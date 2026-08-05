"""V67 Phase 2 — read-only fleet service helpers."""
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fleet_account import FleetAccount
from app.models.fleet_policy import FleetPolicy
from app.models.account import Account
from app.models.incident import AccountIncident
from app.models.instance_state import InstanceLiveState
from app.models.warmup_mesh import WarmupEnrollment
from app.services.fleet_state_adapter import FleetStateAdapter, SensorSnapshot


async def get_fleet_account(db: AsyncSession, account_id: uuid.UUID) -> FleetAccount | None:
    return (await db.execute(
        select(FleetAccount).where(FleetAccount.account_id == account_id)
    )).scalar_one_or_none()


async def list_fleet_accounts(db: AsyncSession, *, limit: int = 200) -> list[FleetAccount]:
    return list((await db.execute(
        select(FleetAccount).order_by(FleetAccount.updated_at.desc()).limit(limit)
    )).scalars().all())


async def get_default_policy(db: AsyncSession) -> FleetPolicy | None:
    return (await db.execute(
        select(FleetPolicy).where(FleetPolicy.is_default.is_(True)).limit(1)
    )).scalar_one_or_none()


async def sensor_mismatch_diagnostics(db: AsyncSession, account_id: uuid.UUID) -> dict:
    acc = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if acc is None:
        return {"error": "account_not_found"}
    fleet = await get_fleet_account(db, account_id)
    enr = None
    if acc.instance_id:
        enr = (await db.execute(
            select(WarmupEnrollment).where(
                WarmupEnrollment.instance_id == str(acc.instance_id),
            ).limit(1)
        )).scalar_one_or_none()
    live = None
    if acc.instance_id:
        live_row = (await db.execute(
            select(InstanceLiveState).where(InstanceLiveState.instance_id == str(acc.instance_id))
        )).scalar_one_or_none()
        live = getattr(live_row, "state", None) if live_row else None
    incidents = list((await db.execute(
        select(AccountIncident.incident_type).where(
            AccountIncident.account_id == account_id,
            AccountIncident.resolved.is_(False),
        )
    )).scalars().all())
    sensors = SensorSnapshot(
        account_status=getattr(acc.status, "value", acc.status),
        warmup_state=getattr(enr, "state", None) if enr else None,
        live_state=live,
        open_incidents=[i for i in incidents if i],
    )
    derived = FleetStateAdapter().derive(sensors, for_seed=True)
    return {
        "account_id": str(account_id),
        "canonical_fleet_state": fleet.fleet_state if fleet else None,
        "recommended_fleet_state": derived.recommended,
        "recommended_reason": derived.reason,
        "legacy_account_status": sensors.account_status,
        "legacy_warmup_state": sensors.warmup_state,
        "live_green_state": sensors.live_state,
        "open_incidents": sensors.open_incidents,
        "mismatches": derived.mismatches,
        "send_gate_note": "send_gate remains runtime authority; FleetState not cut over",
    }
