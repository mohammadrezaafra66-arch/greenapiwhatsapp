"""V19 PART 4 — automatic group-placement engine (runs IN ADDITION to the V17 mesh).

This is a SEPARATE track from the message mesh (warmup_engine.py is not touched). Under the
same enrollment/toggle, it slowly places cold numbers into the user's selected admin groups
on the fixed anti-ban schedule (warmup_group_scheduler.py).

Placement procedure per action:
  1. Pick the next selected target the cold number isn't already in (warm source must be
     authorized/healthy — troubled warm sources are dropped).
  2. Save contacts MUTUALLY (warm admin saves cold; cold saves warm) — required for
     AddGroupParticipant to succeed and legitimate (both are the user's own numbers).
  3. AddGroupParticipant from the warm admin instance.
  4. Read addParticipant: true → 'added'; false → re-save + ONE retry; still false →
     'failed' + error_reason, back off (no hammer loop).

Green API access is via an injected client factory so it unit-tests with mocks and no
network. Nothing here enables polling.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import (
    WarmupEnrollment, WarmupGroupTarget, WarmupGroupMembership, WarmupEventLog,
)
from app.services.green_api import GreenAPIClient
from app.services.warmup_group_scheduler import (
    group_action_due, pick_next_target, count_failed,
)

logger = logging.getLogger("afrakala.warmup.groups.engine")

# Halt ALL group actions for a cold number after this many failed placements (anti-hammer).
GROUP_FAILURE_HALT = 3


def _default_client_factory(instance_id: str, api_token: str) -> GreenAPIClient:
    return GreenAPIClient(instance_id, api_token)


async def _save_mutual_contacts(warm_client, cold_client, warm, cold):
    """Warm(admin) saves cold; cold saves warm. Best-effort — required for AddParticipant."""
    if getattr(cold, "phone", None):
        try:
            await warm_client.add_contact(cold.phone, cold.name or "warmup")
        except Exception as e:
            logger.debug("warm→cold add_contact failed: %s", e)
    if getattr(warm, "phone", None):
        try:
            await cold_client.add_contact(warm.phone, warm.name or "warmup")
        except Exception as e:
            logger.debug("cold→warm add_contact failed: %s", e)


def _added(resp) -> bool:
    return bool(resp.get("addParticipant")) if isinstance(resp, dict) else False


async def place_cold_in_group(db, cold: Account, warm: Account, group_id: str,
                              membership: WarmupGroupMembership, *, client_factory=None,
                              now: datetime | None = None) -> bool:
    """Do ONE group placement: mutual contact save → AddGroupParticipant → (on false)
    re-save + one retry. Updates the membership and writes an audit event. Returns True if
    the cold number was added."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.utcnow()
    warm_client = client_factory(warm.instance_id, warm.api_token)
    cold_client = client_factory(cold.instance_id, cold.api_token)

    await _save_mutual_contacts(warm_client, cold_client, warm, cold)
    membership.attempts = int(membership.attempts or 0) + 1
    membership.last_attempt_at = now
    ok = _added(await warm_client.add_group_participant(group_id, cold.phone))

    if not ok:
        # One retry after re-saving contacts — then stop (no hammer loop).
        await _save_mutual_contacts(warm_client, cold_client, warm, cold)
        membership.attempts += 1
        membership.last_attempt_at = now
        ok = _added(await warm_client.add_group_participant(group_id, cold.phone))

    if ok:
        membership.status = "added"
        membership.added_at = now
        membership.error_reason = None
    else:
        membership.status = "failed"
        membership.error_reason = "addParticipant=false after mutual-save + 1 retry"

    db.add(WarmupEventLog(
        enrollment_id=None, event_type="group_add",
        delivery_status=("added" if ok else "failed"),
        payload_json=json.dumps({"cold": cold.instance_id, "warm": warm.instance_id,
                                 "group": group_id, "ok": ok, "attempts": membership.attempts},
                                ensure_ascii=False),
    ))
    return ok


async def _memberships_for(db, cold_instance_id: str) -> list:
    return (await db.execute(
        select(WarmupGroupMembership).where(WarmupGroupMembership.cold_instance_id == cold_instance_id)
    )).scalars().all()


async def run_group_warmup_tick(db, now: datetime | None = None, *, client_factory=None) -> dict:
    """One group-warmup beat: for each ENROLLED cold number whose owner selected group
    targets, do at most ONE scheduled, capped, spaced group placement. Halts on the V17
    chain-ban breaker and on paused/carded/blocked numbers."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.utcnow()

    from app.services.warmup_killswitch import is_breaker_tripped
    if await is_breaker_tripped(db, now):
        return {"acted": 0, "halted": True, "reason": "breaker"}

    targets = (await db.execute(
        select(WarmupGroupTarget).where(WarmupGroupTarget.is_selected.is_(True))
    )).scalars().all()
    if not targets:
        return {"acted": 0, "targets": 0}

    enrollments = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.is_enabled.is_(True))
    )).scalars().all()

    # Index accounts by instance for warm-source health + cold lookup.
    accounts = {a.instance_id: a for a in (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()}

    # Drop targets whose warm (admin) source is not currently authorized/healthy.
    healthy_targets = [t for t in targets if accounts.get(t.warm_instance_id)]

    acted = skipped = 0
    for enr in enrollments:
        cold = accounts.get(enr.instance_id)
        if not cold:
            skipped += 1
            continue                                  # cold not authorized/active → halt its group actions
        memberships = await _memberships_for(db, enr.instance_id)
        # Anti-hammer / kill-switch: too many failed placements → stop this cold's group track.
        if count_failed(memberships) >= GROUP_FAILURE_HALT:
            skipped += 1
            continue
        due, reason = group_action_due(enr, memberships, now)
        if not due:
            skipped += 1
            continue
        target = pick_next_target(enr.instance_id, healthy_targets, memberships)
        if target is None:
            skipped += 1
            continue
        warm = accounts.get(target.warm_instance_id)
        if not warm:
            skipped += 1
            continue
        membership = WarmupGroupMembership(
            cold_instance_id=enr.instance_id, warm_instance_id=warm.instance_id,
            group_id=target.group_id, status="pending",
        )
        db.add(membership)
        await place_cold_in_group(db, cold, warm, target.group_id, membership,
                                  client_factory=client_factory, now=now)
        acted += 1

    await db.commit()
    return {"acted": acted, "skipped": skipped, "targets": len(targets)}
