"""V41 PART 4 — enroll a number into mesh RECOVERY mode + safe-peer selection.

A scoped, single-account exception: enroll ONE number (default 7105325764) into the existing
mesh state machine in recovery_mode (COOLDOWN, day 0), leaving every OTHER account's enrollment
untouched (mesh stays globally disabled for everyone else). Two decisions are deliberately NOT
made silently and instead surfaced for an explicit human choice:

  1. If the chain-ban circuit breaker is currently tripped, this NEVER silently resets it — it
     halts and reports (weakening the breaker is exactly what would re-chain a ban).
  2. Peer selection reuses the EXISTING peer-eligibility + warmth logic. If NO currently-connected
     account passes the existing bar, it reports "none qualify" rather than picking an ineligible
     peer; relaxing the bar for a monitored recovery cycle is a visible human choice, not a default.

Pure-ish + injectable so it unit-tests against the repo's FakeSession with no network.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment, WarmupEventLog
from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG
from app.services.warmup_killswitch import is_breaker_tripped
from app.services.warmup_mesh_service import eligible_peer_accounts, is_peer_healthy
from app.services.warmup_peer_eligibility import check_peer_eligibility
from app.services.warmup_warmth import warmth_for_account
from app.services.warmup_exclusion import enrollment_states_by_instance

logger = logging.getLogger("afrakala.warmup.recovery_enroll")

# The single account this recovery cycle is for (9122270261 / instance 7105325764). The functions
# accept any target so the same flow can be reused for a different number later.
RECOVERY_TARGET_INSTANCE = "7105325764"


# ── peer selection (reuses the existing eligibility + warmth logic) ──────────
async def rank_peer_candidates(db, target_instance_id: str,
                               now: datetime | None = None) -> list[dict]:
    """Rank the EXISTING mesh peer pool (is_warm_peer OR GRADUATED accounts, active, not the
    target itself) as candidate peers for the recovery target. Each candidate carries the
    existing peer-eligibility verdict (>=14-day + clean history), whether it is usable right now
    (healthy), and its 0-100 warmth score. Safest first: eligible-and-healthy outrank the rest,
    then higher warmth. Reuses V27/V29 evaluators — no parallel logic."""
    now = now or datetime.utcnow()
    pool = await eligible_peer_accounts(db, target_instance_id)
    out: list[dict] = []
    for a in pool:
        eligible, reason, _msg = await check_peer_eligibility(db, a, now)
        warmth = await warmth_for_account(db, a, now)
        healthy = is_peer_healthy(a, now)
        out.append({
            "instance_id": a.instance_id,
            "name": getattr(a, "name", None),
            "phone": getattr(a, "phone", None),
            "peer_eligible": bool(eligible),
            "reason": reason,
            "healthy": bool(healthy),
            "warmth_score": warmth["score"],
            "warmth_level": warmth["level"],
            "age_days": warmth.get("age_days"),
            "safe": bool(eligible) and bool(healthy),
        })
    out.sort(key=lambda c: (c["safe"], c["warmth_score"]), reverse=True)
    return out


async def select_safe_peer(db, target_instance_id: str,
                           now: datetime | None = None) -> dict:
    """Report the SAFEST currently-connected eligible peer for the recovery target, or the
    explicit "none qualify" finding. Never silently returns an ineligible peer.
    Returns {qualifies, peer|None, candidates:[...]}."""
    candidates = await rank_peer_candidates(db, target_instance_id, now)
    safe = [c for c in candidates if c["safe"]]
    return {"qualifies": bool(safe), "peer": safe[0] if safe else None,
            "candidates": candidates}


# ── enrollment (recovery mode, day 0), with the two hard stops ───────────────
async def _snapshot_other_enabled(db, target_instance_id: str) -> dict:
    """{instance_id: is_enabled} for every enrollment EXCEPT the target (guardrail 2 evidence)."""
    m = await enrollment_states_by_instance(db)
    return {iid: enabled for iid, (_state, enabled) in m.items() if iid != target_instance_id}


async def enroll_recovery_mode(db, target_instance_id: str = RECOVERY_TARGET_INSTANCE,
                               now: datetime | None = None, *,
                               commit: bool = True) -> dict:
    """Enroll `target_instance_id` into the mesh in RECOVERY mode: is_enabled=true, COOLDOWN,
    day_index=0, recovery_mode=true. Confirms every OTHER enrollment's is_enabled is unchanged.

    HARD STOP: if the chain-ban breaker is tripped, does NOT enroll and does NOT reset the breaker
    — returns {halted:true, reason:"breaker_tripped"} for a human decision. Never enables polling,
    never touches any other account's enrollment."""
    now = now or datetime.utcnow()
    cfg = DEFAULT_WARMUP_CONFIG

    # HARD STOP 1 — never proceed (or silently reset) while the breaker is tripped.
    if await is_breaker_tripped(db, now):
        logger.warning("recovery enroll halted for %s: chain-ban breaker tripped", target_instance_id)
        return {"enrolled": False, "halted": True, "reason": "breaker_tripped",
                "instance_id": target_instance_id}

    before = await _snapshot_other_enabled(db, target_instance_id)

    enr = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == target_instance_id)
    )).scalar_one_or_none()
    acc = (await db.execute(
        select(Account).where(Account.instance_id == target_instance_id)
    )).scalar_one_or_none()
    created = False
    if enr is None:
        enr = WarmupEnrollment(instance_id=target_instance_id,
                               phone=getattr(acc, "phone", None),
                               state=WarmupState.ENROLLED.value, day_index=0)
        db.add(enr)
        await db.flush()
        created = True

    # Recovery enrollment: day 0 / COOLDOWN / recovery_mode. Re-anchor day counters to now (the
    # number is authorized/connected now → the 24h COOLDOWN + Day-1 no-send both hold).
    enr.recovery_mode = True
    enr.is_enabled = True
    enr.state = WarmupState.COOLDOWN.value
    enr.day_index = 0
    enr.started_at = now
    enr.authorized_at = now
    enr.sent_today = 0
    enr.received_today = 0
    enr.reply_ratio = 0.0
    enr.rest_until = None
    enr.next_action_at = now + timedelta(hours=cfg.cooldown_hours)
    if getattr(acc, "phone", None):
        enr.phone = acc.phone

    db.add(WarmupEventLog(
        enrollment_id=enr.id, event_type="state_change",
        payload_json='{"to": "COOLDOWN", "reason": "v41_recovery_enroll", "recovery_mode": true}'))

    after = await _snapshot_other_enabled(db, target_instance_id)
    others_unchanged = before == after
    others_enabled = [iid for iid, en in after.items() if en]
    if not others_unchanged or others_enabled:
        # Guardrail 2 — we must never have flipped another account on. This is defensive: this
        # function only ever writes the target enrollment, so a mismatch means something else did.
        logger.error("recovery enroll guardrail: other enrollments changed/enabled: before=%s after=%s",
                     before, after)

    if commit:
        await db.commit()

    return {"enrolled": True, "halted": False, "instance_id": target_instance_id,
            "created": created, "state": enr.state, "day_index": enr.day_index,
            "recovery_mode": enr.recovery_mode, "is_enabled": enr.is_enabled,
            "cooldown_until": enr.next_action_at.isoformat() if enr.next_action_at else None,
            "others_unchanged": others_unchanged, "other_enabled_instances": others_enabled}
