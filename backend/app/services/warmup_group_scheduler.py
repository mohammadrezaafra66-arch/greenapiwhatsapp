"""V19 PART 4 — FIXED, standards-based group-action schedule (NOT user-configurable).

Pure decision logic (no DB/network/Celery) so the whole conservative anti-ban schedule
unit-tests deterministically. The async engine (warmup_group_engine.py) composes these.

Schedule (per cold number, keyed off its V17 warm-up state/day):
  • Day 0–1 (COOLDOWN) & Days 2–3 (RECEIVING): ZERO group actions.
  • Day 4 (REPLYING): first group action allowed — 1 admin group, waking hours only.
  • Days 5–10 (RAMPING): ≤1 group action/day, ≤5 total memberships in the first 10 days,
    ≥48h between actions.
  • Day 10+ (MATURING): slow to ~1 group every 3–10 days.
Global caps (always): ≤1 group action/cold-number/day; ≥48h between actions (target; the
research floor is 24h — we ship the stricter 48h); waking hours 09:00–21:00 Asia/Tehran;
never two groups in one session; mutual-contact save before every add (enforced in engine).
"""
from __future__ import annotations
import random
from datetime import datetime, timedelta

from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG
from app.services.warmup_scheduler import day_index, target_state_for_day, in_active_hours, _naive

# FIXED constants — shipped, not user-configurable.
GROUP_FIRST_ACTION_DAY = 4          # first group action at Day 4 (REPLYING)
GROUP_MAX_PER_DAY = 1               # never more than 1 group action per cold number per day
GROUP_MAX_IN_FIRST_10_DAYS = 5      # ≤5 total memberships across the first 10 days
GROUP_MIN_SPACING_HOURS = 48        # ≥48h between any two group actions (stricter than the 24h floor)
GROUP_MATURING_MIN_DAYS = 3         # Day 10+: ~1 every 3–10 days → floor 3 days
GROUP_MATURING_MAX_DAYS = 10

_HALT_STATES = {WarmupState.PAUSED.value, WarmupState.YELLOWCARD.value, WarmupState.BLOCKED_RESET.value}


def _action_ts(m):
    """The time a membership represents an action (added or last attempted), or None."""
    return getattr(m, "added_at", None) or getattr(m, "last_attempt_at", None)


def is_group_action(m) -> bool:
    """A membership that reflects a real group action (added, or attempted at least once)."""
    return getattr(m, "status", None) == "added" or int(getattr(m, "attempts", 0) or 0) > 0


def count_actions_today(memberships, now: datetime) -> int:
    today = _naive(now).date()
    n = 0
    for m in memberships:
        ts = _action_ts(m)
        if ts is not None and _naive(ts).date() == today:
            n += 1
    return n


def last_action_at(memberships):
    times = [_action_ts(m) for m in memberships if _action_ts(m) is not None]
    return max(times, key=lambda t: _naive(t)) if times else None


def count_group_actions(memberships) -> int:
    """Total real group actions taken (used for the first-10-days cap)."""
    return sum(1 for m in memberships if is_group_action(m))


def count_failed(memberships) -> int:
    return sum(1 for m in memberships if getattr(m, "status", None) == "failed")


def group_action_due(enrollment, memberships, now: datetime,
                     cfg=DEFAULT_WARMUP_CONFIG) -> tuple[bool, str]:
    """Is a group action allowed for this cold number right now? Returns (allowed, reason)."""
    state = getattr(enrollment, "state", "")
    if state in _HALT_STATES:
        return False, "paused_or_carded"            # kill-switch: yellowCard/block/paused → halt
    day = day_index(enrollment, now)
    eff_state = target_state_for_day(day, state, cfg)
    if eff_state in _HALT_STATES:
        return False, "paused_or_carded"
    # Day 0–3: COOLDOWN + RECEIVING → zero group actions.
    if day < GROUP_FIRST_ACTION_DAY:
        return False, "before_day_4"
    # Waking hours only.
    if not in_active_hours(now, cfg):
        return False, "outside_waking"
    # ≤1 group action per day.
    if count_actions_today(memberships, now) >= GROUP_MAX_PER_DAY:
        return False, "daily_cap"
    # ≥48h spacing between actions.
    last = last_action_at(memberships)
    if last is not None and (_naive(now) - _naive(last)) < timedelta(hours=GROUP_MIN_SPACING_HOURS):
        return False, "spacing_48h"
    # ≤5 total memberships in the first 10 days.
    if day <= 10 and count_group_actions(memberships) >= GROUP_MAX_IN_FIRST_10_DAYS:
        return False, "ten_day_cap"
    # Day 10+: slow to ~1 every 3–10 days (floor 3 days).
    if day > 10 and last is not None and (_naive(now) - _naive(last)) < timedelta(days=GROUP_MATURING_MIN_DAYS):
        return False, "maturing_spacing"
    return True, "ok"


def pick_next_target(cold_instance_id: str, targets, memberships,
                     rng: random.Random | None = None):
    """Pick the next selected admin-group target this cold number isn't already placed in /
    attempted (added/failed/pending all excluded → never re-hammer). Returns a target or None."""
    touched = {getattr(m, "group_id", None) for m in memberships}
    candidates = [t for t in targets
                  if getattr(t, "is_selected", True) and getattr(t, "group_id", None) not in touched]
    if not candidates:
        return None
    r = rng or random
    return candidates[r.randrange(len(candidates))]


def next_group_action_eta(enrollment, now: datetime, cfg=DEFAULT_WARMUP_CONFIG,
                          rng: random.Random | None = None) -> datetime:
    """A human-facing estimate of when the next group action becomes eligible (for the
    dashboard): +48h in RAMPING, a random 3–10 days in MATURING."""
    day = day_index(enrollment, now)
    if day > 10:
        r = rng or random
        return now + timedelta(days=r.randint(GROUP_MATURING_MIN_DAYS, GROUP_MATURING_MAX_DAYS))
    return now + timedelta(hours=GROUP_MIN_SPACING_HOURS)
