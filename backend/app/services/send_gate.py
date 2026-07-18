"""V27 PART 1 — the ONE pre-send health gate.

`can_send_now(account)` is the SINGLE source of truth for "may this instance send a message
right this moment". EVERY send call-site (mesh warm-up, campaign runner, group auto-reply,
helper-assist) must call it IMMEDIATELY before hitting Green API's sendMessage — not just at
scheduling time, because an instance can be carded between scheduling and execution (exactly
the live incident: a carded warm peer kept sending 19 more messages).

It checks, in order (Green API's own health signals, most-authoritative first):
  1. status == active
  2. cooldown_until is not in the future   (yellowCard cooldown → hard stop)
  3. throttle window not active            (an active anti-ban throttle → hold)
  4. the LIVE Green API state is not yellowCard/blocked/notAuthorized

The live state comes from a fast in-memory mirror kept fresh by PART 4's ~60s poll and the
state-change webhook (see refresh_live_state / update_live_state). Reading the mirror is a
plain dict lookup — it never touches the DB session, so it can't disturb the FakeSession
result queues the warm-up/campaign unit-tests rely on. When no fresh live state is known the
gate still enforces 1–3 (the cooldown set by the incident handler already blocks a carded
instance), so it degrades safe, never open.
"""
from __future__ import annotations
import logging
from datetime import datetime

from app.services import governors

logger = logging.getLogger("afrakala.send_gate")

# Live Green API states that must block sending immediately (lower-cased for comparison).
BLOCKING_LIVE_STATES = {"yellowcard", "blocked", "notauthorized", "notauthorised", "starting"}
# States we treat as a hard-danger signal that should ALSO trip the per-instance kill-switch.
KILL_LIVE_STATES = {"yellowcard", "blocked", "notauthorized", "notauthorised"}

# How fresh a cached live state must be to be trusted by the gate (matches PART 4's ~60s poll
# cadence — a just-carded instance is caught within roughly a minute).
LIVE_STATE_MAX_AGE_SECONDS = 90

# In-memory mirror of the durable instance_live_state table: {instance_id: (state_lc, checked_at)}.
# Populated by PART 4's poll task and the state-change webhook. Empty after a fresh process
# start (the gate then relies on cooldown/throttle until the next poll repopulates it).
_live_cache: dict[str, tuple[str, datetime]] = {}


_MISSING = object()


def _status_value(account) -> str | None:
    # A real Account ALWAYS carries `status`; lightweight objects that simply don't model it
    # (e.g. test doubles) are not gated on status — the cooldown/throttle/live-state checks
    # still apply. This keeps production fully gated without forcing every helper object to
    # carry a status field.
    status = getattr(account, "status", _MISSING)
    if status is _MISSING:
        return "active"
    return getattr(status, "value", status)


def update_live_state(instance_id: str, state: str, checked_at: datetime | None = None) -> None:
    """Record a freshly-observed live state in the in-memory mirror (called by the PART 4
    poll and the state-change webhook). `state` is stored lower-cased."""
    if not instance_id:
        return
    _live_cache[str(instance_id)] = ((state or "unknown").strip().lower(),
                                     checked_at or datetime.utcnow())


def get_cached_live_state(instance_id: str, now: datetime | None = None,
                          max_age_seconds: int = LIVE_STATE_MAX_AGE_SECONDS) -> str | None:
    """The last-known live state for an instance IF it is fresh enough to trust, else None."""
    now = now or datetime.utcnow()
    entry = _live_cache.get(str(instance_id))
    if not entry:
        return None
    state, checked_at = entry
    if checked_at is None:
        return None
    if (now - checked_at).total_seconds() > max_age_seconds:
        return None
    return state


def clear_live_cache() -> None:
    """Test helper — wipe the in-memory mirror."""
    _live_cache.clear()


def can_send_now(account, live_state: str | None = None,
                 now: datetime | None = None) -> tuple[bool, str]:
    """PURE gate. Returns (allowed, reason). `live_state` (if given) is the instance's live
    Green API state; pass None when unknown (the gate still enforces status/cooldown/throttle).
    reason is a stable slug: not_active | cooldown | throttled | live_state:<s> | ok."""
    now = now or datetime.utcnow()
    if _status_value(account) != "active":
        return False, "not_active"
    if governors.in_cooldown(account, now):
        return False, "cooldown"
    if governors.is_throttled(account, now):
        return False, "throttled"
    if live_state is not None:
        s = str(live_state).strip().lower()
        if s in BLOCKING_LIVE_STATES:
            return False, f"live_state:{s}"
    return True, "ok"


def gate_check(account, now: datetime | None = None) -> tuple[bool, str]:
    """The gate as every send call-site should use it: resolves the instance's fresh live
    state from the in-memory mirror (no DB hit) and applies can_send_now. Synchronous and
    side-effect-free so it is safe to call in any path, including FakeSession unit-tests."""
    now = now or datetime.utcnow()
    live = get_cached_live_state(getattr(account, "instance_id", None), now)
    allowed, reason = can_send_now(account, live, now)
    if not allowed:
        logger.info("send gate blocked %s: %s", getattr(account, "instance_id", "?"), reason)
    return allowed, reason


def is_kill_reason(reason: str) -> bool:
    """True when a gate refusal was caused by a live danger state that should also trip the
    per-instance kill-switch (so nothing else tries to use the instance either)."""
    if not reason or not reason.startswith("live_state:"):
        return False
    return reason.split(":", 1)[1] in KILL_LIVE_STATES


# ── durable persistence + kill-switch trip (async; used where a real DB session exists) ──
async def persist_live_state(db, instance_id: str, state: str, source: str,
                             now: datetime | None = None) -> None:
    """Upsert the durable instance_live_state row AND refresh the in-memory mirror. Best-effort:
    any failure is swallowed so state monitoring can never break a send/poll path."""
    from sqlalchemy import select
    from app.models.instance_state import InstanceLiveState
    now = now or datetime.utcnow()
    state_lc = (state or "unknown").strip().lower()
    update_live_state(instance_id, state_lc, now)
    try:
        row = (await db.execute(
            select(InstanceLiveState).where(InstanceLiveState.instance_id == str(instance_id))
        )).scalar_one_or_none()
        if row is None:
            db.add(InstanceLiveState(instance_id=str(instance_id), state=state_lc,
                                     source=source, checked_at=now))
        else:
            row.state = state_lc
            row.source = source
            row.checked_at = now
    except Exception as e:  # pragma: no cover - durability is best-effort
        logger.warning("persist_live_state failed for %s: %s", instance_id, e)


async def trip_kill_switch_for(db, account, reason: str, now: datetime | None = None) -> None:
    """Immediately quarantine an instance the gate found live-unhealthy: route a yellowCard
    through the existing automatic incident response (send-stop + cooldown + throttle), and a
    block/notAuthorized straight to a hard cooldown. Reuses the V14 kill-switch — never a new,
    weaker path. No-op unless `reason` is a live danger state."""
    if not is_kill_reason(reason):
        return
    state = reason.split(":", 1)[1]
    now = now or datetime.utcnow()
    try:
        if state == "yellowcard":
            from app.services.incident_handler import handle_yellow_card
            await handle_yellow_card(account, "gate", db)
        else:
            from datetime import timedelta
            from app.services import governors
            account.throttle_factor = governors.YELLOW_THROTTLE_FACTOR
            account.throttle_until = now + timedelta(days=7)
            account.cooldown_until = now + timedelta(days=1)
            account.last_incident_at = now
    except Exception as e:  # pragma: no cover
        logger.warning("trip_kill_switch_for %s failed: %s",
                       getattr(account, "instance_id", "?"), e)

