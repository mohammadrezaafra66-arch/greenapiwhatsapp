"""V67 Phase 2 — idempotent fleet seed / backfill (dry-run by default).

Never auto-grants CAMPAIGN_READY or MATURE.
Never runs against production unless operator passes --apply explicitly.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.fleet_account import FleetAccount
from app.models.fleet_policy import FleetPolicy
from app.models.incident import AccountIncident
from app.models.instance_state import InstanceLiveState
from app.models.warmup_mesh import WarmupEnrollment
from app.services.fleet_policy_defaults import (
    CONSERVATIVE_POLICY_SETTINGS, validate_policy_settings,
)
from app.services.fleet_state import FleetState, SEED_FORBIDDEN_AUTO_STATES
from app.services.fleet_state_adapter import FleetStateAdapter, SensorSnapshot


@dataclass
class SeedPlanRow:
    account_id: str
    instance_id: str | None
    action: str  # create | update | skip
    from_state: str | None
    to_state: str
    reason: str
    mismatches: list[str]


async def ensure_default_conservative_policy(db: AsyncSession) -> FleetPolicy:
    """Idempotent: one default CONSERVATIVE v1 policy."""
    existing = (await db.execute(
        select(FleetPolicy).where(
            FleetPolicy.name == "CONSERVATIVE",
            FleetPolicy.version == 1,
        )
    )).scalar_one_or_none()
    if existing:
        return existing
    ok, msg = validate_policy_settings(CONSERVATIVE_POLICY_SETTINGS)
    if not ok:
        raise ValueError(f"invalid conservative settings: {msg}")
    # Clear other defaults if any (should be none on first seed)
    others = (await db.execute(
        select(FleetPolicy).where(FleetPolicy.is_default.is_(True))
    )).scalars().all()
    for o in others:
        o.is_default = False
    row = FleetPolicy(
        id=uuid.uuid4(),
        name="CONSERVATIVE",
        version=1,
        is_active=True,
        is_default=True,
        policy_type="CONSERVATIVE",
        settings_json=dict(CONSERVATIVE_POLICY_SETTINGS),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    await db.flush()
    return row


async def _open_incident_types(db: AsyncSession, account_id: uuid.UUID) -> list[str]:
    rows = (await db.execute(
        select(AccountIncident.incident_type).where(
            AccountIncident.account_id == account_id,
            AccountIncident.resolved.is_(False),
        )
    )).scalars().all()
    return [r for r in rows if r]


async def _warmup_enrollment(db: AsyncSession, instance_id: str | None):
    if not instance_id:
        return None
    enr = (await db.execute(
        select(WarmupEnrollment).where(
            WarmupEnrollment.instance_id == str(instance_id),
            WarmupEnrollment.is_enabled.is_(True),
        ).limit(1)
    )).scalar_one_or_none()
    if enr is None:
        enr = (await db.execute(
            select(WarmupEnrollment).where(
                WarmupEnrollment.instance_id == str(instance_id),
            ).limit(1)
        )).scalar_one_or_none()
    return enr


async def _live_state(db: AsyncSession, instance_id: str | None) -> str | None:
    if not instance_id:
        return None
    row = (await db.execute(
        select(InstanceLiveState).where(InstanceLiveState.instance_id == str(instance_id))
    )).scalar_one_or_none()
    return getattr(row, "state", None) if row else None


async def build_seed_plan(
    db: AsyncSession,
    *,
    account_id: uuid.UUID | None = None,
    batch_size: int = 200,
    fleet_breaker_tripped: bool = False,
) -> list[SeedPlanRow]:
    adapter = FleetStateAdapter()
    if account_id is not None:
        q = select(Account).where(Account.id == account_id)
    else:
        q = select(Account).order_by(Account.created_at.asc()).limit(batch_size)
    accounts = list((await db.execute(q)).scalars().all())
    plans: list[SeedPlanRow] = []
    for acc in accounts:
        incidents = await _open_incident_types(db, acc.id)
        enr = await _warmup_enrollment(db, getattr(acc, "instance_id", None))
        warmup = getattr(enr, "state", None) if enr else None
        live = await _live_state(db, getattr(acc, "instance_id", None))
        sensors = SensorSnapshot(
            account_status=getattr(getattr(acc, "status", None), "value", acc.status),
            warmup_state=warmup,
            live_state=live,
            open_incidents=incidents,
            fleet_breaker_tripped=fleet_breaker_tripped,
            days_active=getattr(acc, "days_active", None),
            has_real_inbound=(getattr(acc, "received_today", 0) or 0) > 0,
            has_real_outbound=(getattr(acc, "sent_today", 0) or 0) > 0,
            recovery_mode=bool(getattr(enr, "recovery_mode", False)) if enr else False,
        )
        derived = adapter.derive(sensors, for_seed=True)
        assert derived.recommended not in SEED_FORBIDDEN_AUTO_STATES

        existing = (await db.execute(
            select(FleetAccount).where(FleetAccount.account_id == acc.id)
        )).scalar_one_or_none()
        if existing is None:
            plans.append(SeedPlanRow(
                account_id=str(acc.id),
                instance_id=getattr(acc, "instance_id", None),
                action="create",
                from_state=None,
                to_state=derived.recommended,
                reason=derived.reason,
                mismatches=list(derived.mismatches),
            ))
        elif existing.fleet_state == derived.recommended:
            plans.append(SeedPlanRow(
                account_id=str(acc.id),
                instance_id=getattr(acc, "instance_id", None),
                action="skip",
                from_state=existing.fleet_state,
                to_state=derived.recommended,
                reason="idempotent_unchanged",
                mismatches=list(derived.mismatches),
            ))
        else:
            # Idempotent seed: do not thrash operator-set later states; only fill if still NEW/PRECHECK
            if existing.fleet_state in (FleetState.NEW.value, FleetState.PRECHECK.value):
                plans.append(SeedPlanRow(
                    account_id=str(acc.id),
                    instance_id=getattr(acc, "instance_id", None),
                    action="update",
                    from_state=existing.fleet_state,
                    to_state=derived.recommended,
                    reason=derived.reason,
                    mismatches=list(derived.mismatches),
                ))
            else:
                plans.append(SeedPlanRow(
                    account_id=str(acc.id),
                    instance_id=getattr(acc, "instance_id", None),
                    action="skip",
                    from_state=existing.fleet_state,
                    to_state=existing.fleet_state,
                    reason="preserve_existing_non_seed_state",
                    mismatches=list(derived.mismatches),
                ))
    return plans


async def apply_seed_plan(
    db: AsyncSession,
    plans: list[SeedPlanRow],
    *,
    policy: FleetPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or await ensure_default_conservative_policy(db)
    now = datetime.utcnow()
    created = updated = skipped = 0
    for p in plans:
        if p.action == "skip":
            skipped += 1
            continue
        aid = uuid.UUID(p.account_id)
        if p.action == "create":
            db.add(FleetAccount(
                id=uuid.uuid4(),
                account_id=aid,
                fleet_state=p.to_state,
                policy_id=policy.id,
                state_reason=p.reason,
                state_changed_at=now,
                version=1,
                created_at=now,
                updated_at=now,
            ))
            created += 1
        elif p.action == "update":
            row = (await db.execute(
                select(FleetAccount).where(FleetAccount.account_id == aid)
            )).scalar_one()
            row.fleet_state = p.to_state
            row.state_reason = p.reason
            row.state_changed_at = now
            row.version = int(row.version or 1) + 1
            row.updated_at = now
            if row.policy_id is None:
                row.policy_id = policy.id
            updated += 1
    await db.flush()
    return {"created": created, "updated": updated, "skipped": skipped, "policy_id": str(policy.id)}


def plans_as_dicts(plans: list[SeedPlanRow]) -> list[dict]:
    return [asdict(p) for p in plans]
