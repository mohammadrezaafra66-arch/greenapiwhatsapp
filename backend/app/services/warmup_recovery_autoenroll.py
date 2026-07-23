"""V41 Path B — automated wait-and-apply for the mesh recovery enrollment of 7105325764.

This module does NOT introduce any new rule and NEVER relaxes an existing one. It only automates
WHEN the already-built, already-tested preflight/enroll logic runs:

  • the chain-ban breaker check  → app.services.warmup_killswitch.is_breaker_tripped  (unchanged)
  • the peer-eligibility check    → app.services.warmup_recovery_enroll.select_safe_peer (unchanged,
    which reuses the >=14-day-clean peer-eligibility + warmth evaluators)
  • the enrollment itself         → app.services.warmup_recovery_enroll.enroll_recovery_mode (unchanged)

`run_recovery_autoenroll_check` is invoked once a day by a Celery beat task. Each run:
  1. is a safe no-op if 7105325764 is already enrolled in recovery mode (idempotent — fires once);
  2. re-verifies (guardrail) that no OTHER account's mesh enrollment has been enabled — if one has,
     it ABORTS the auto-apply for this run and logs a loud warning, changing nothing;
  3. if the breaker is tripped OR no account passes the existing peer bar, does nothing but log a
     one-line status (so there is a visible history of when the conditions changed);
  4. only when BOTH conditions are genuinely clear under the existing rules, auto-applies the
     recovery enrollment via the existing enroll_recovery_mode (is_enabled=true, COOLDOWN, day 0,
     recovery_mode=true, peer=the found eligible account).

It NEVER resets the breaker and NEVER relaxes the peer bar — both must clear naturally through the
existing, unmodified logic. Every run records a durable `recovery_recheck` event so the dashboard
can show the latest finding without a fresh diagnostic.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

from sqlalchemy import select

from app.models.warmup_mesh import WarmupEnrollment, WarmupEventLog
from app.services.warmup_killswitch import is_breaker_tripped
from app.services.warmup_recovery_enroll import (
    RECOVERY_TARGET_INSTANCE, select_safe_peer, enroll_recovery_mode,
)
from app.services.warmup_exclusion import enrollment_states_by_instance

logger = logging.getLogger("afrakala.warmup.recovery_autoenroll")

# The durable event that records each recheck's finding (breaker/peer/applied), read by the dashboard.
RECHECK_EVENT = "recovery_recheck"


async def _load_target_enrollment(db, target: str) -> WarmupEnrollment | None:
    """The target's current enrollment row, or None if it was never enrolled. Isolated so tests can
    substitute it and so the single DB read is easy to reason about."""
    return (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == target)
    )).scalar_one_or_none()


def _record_status(db, payload: dict) -> None:
    """Persist one recheck finding as a durable event the dashboard reads (never an action itself)."""
    db.add(WarmupEventLog(enrollment_id=None, event_type=RECHECK_EVENT,
                          payload_json=json.dumps(payload, ensure_ascii=False)))


async def run_recovery_autoenroll_check(db, now: datetime | None = None,
                                        target: str = RECOVERY_TARGET_INSTANCE,
                                        *, commit: bool = True) -> dict:
    """Run one automated recheck for `target`. Returns the finding dict (also recorded as an event).

    Reuses the EXISTING breaker/peer/enroll logic verbatim; this function only decides WHEN to call
    it. Never resets the breaker, never relaxes the peer bar, never touches another account."""
    now = now or datetime.utcnow()
    enr = await _load_target_enrollment(db, target)
    already_enrolled = bool(enr is not None
                            and getattr(enr, "recovery_mode", False)
                            and getattr(enr, "is_enabled", False))

    breaker = await is_breaker_tripped(db, now)
    peer_res = await select_safe_peer(db, target, now)
    peer_ok = bool(peer_res.get("qualifies"))
    peer = peer_res.get("peer")
    peer_instance = peer.get("instance_id") if isinstance(peer, dict) else None

    others = await enrollment_states_by_instance(db)
    other_enabled = [iid for iid, (_state, enabled) in others.items()
                     if iid != target and enabled]

    base = {
        "target": target,
        "breaker_tripped": bool(breaker),
        "peer_qualifies": peer_ok,
        "peer_instance": peer_instance,
        "other_enabled_instances": other_enabled,
        "at": now.isoformat(),
    }

    # (1) Idempotency — already enrolled in recovery mode → safe no-op (the task only needs to fire
    # once, but must never error or re-apply if it runs again).
    if already_enrolled:
        status = {**base, "applied": False, "already_enrolled": True, "action": "noop_already_enrolled",
                  "message": "recovery enrollment already applied — no-op"}
        _record_status(db, status)
        logger.info("[recovery-autoenroll] %s already enrolled in recovery mode — no-op", target)
        if commit:
            await db.commit()
        return status

    # (2) Guardrail — before applying anything, EVERY other account's mesh enrollment must still be
    # disabled. If one was enabled by some other process, abort the auto-apply and warn loudly.
    if not breaker and peer_ok and other_enabled:
        status = {**base, "applied": False, "aborted_guardrail": True, "action": "abort_other_enabled",
                  "message": f"AUTO-APPLY ABORTED: other mesh enrollments unexpectedly enabled: {other_enabled}"}
        _record_status(db, status)
        logger.error("[recovery-autoenroll] ABORT: other accounts have mesh enabled (%s) — not "
                     "auto-applying recovery enrollment for %s this run", other_enabled, target)
        if commit:
            await db.commit()
        return status

    # (3) Either condition still not met → do nothing but log a one-line status.
    if breaker or not peer_ok:
        msg = (f"recovery enrollment still blocked: "
               f"breaker={'tripped' if breaker else 'clear'}, "
               f"peer={'none' if not peer_ok else 'found ' + str(peer_instance)}")
        status = {**base, "applied": False, "blocked": True, "action": "blocked", "message": msg}
        _record_status(db, status)
        logger.info("[recovery-autoenroll] %s", msg)
        if commit:
            await db.commit()
        return status

    # (4) BOTH conditions clear + no other account enabled → auto-apply via the EXISTING enroller.
    # commit=False so the enrollment + this status row land in one transaction. enroll_recovery_mode
    # re-checks the breaker itself (belt-and-suspenders) and never resets it.
    result = await enroll_recovery_mode(db, target, now, commit=False)
    if result.get("halted"):
        status = {**base, "applied": False, "blocked": True, "action": "blocked_on_apply",
                  "message": f"recovery enrollment halted by existing guard at apply: {result.get('reason')}"}
        _record_status(db, status)
        logger.warning("[recovery-autoenroll] apply halted for %s: %s", target, result.get("reason"))
        if commit:
            await db.commit()
        return status

    status = {**base, "applied": True, "action": "auto_applied",
              "peer_instance": peer_instance,
              "state": result.get("state"), "day_index": result.get("day_index"),
              "recovery_mode": result.get("recovery_mode"), "is_enabled": result.get("is_enabled"),
              "others_unchanged": result.get("others_unchanged"),
              "message": (f"recovery enrollment AUTO-APPLIED for {target}: not-enrolled -> "
                          f"COOLDOWN/day0/recovery_mode, peer={peer_instance} "
                          f"(safest eligible+healthy peer under the existing bar)")}
    _record_status(db, status)
    logger.warning("[recovery-autoenroll] AUTO-APPLIED recovery enrollment for %s with peer %s "
                   "(both conditions cleared naturally)", target, peer_instance)
    if commit:
        await db.commit()
    return status


async def latest_recheck_status(db, target: str = RECOVERY_TARGET_INSTANCE) -> dict | None:
    """The most recent recorded recheck finding (parsed), or None if no recheck has run yet.
    Read-only; used by the dashboard to show the pending state without a fresh diagnostic."""
    row = (await db.execute(
        select(WarmupEventLog).where(WarmupEventLog.event_type == RECHECK_EVENT)
        .order_by(WarmupEventLog.created_at.desc())
    )).scalars().first()
    if row is None:
        return None
    try:
        return json.loads(row.payload_json or "{}")
    except Exception:
        return None
