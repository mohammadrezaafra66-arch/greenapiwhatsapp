"""V41 PART 1 — recovery-mode timeline matches Green API's exact 10-day recovery sequence.

Proves:
  • a recovery-mode enrollment's day-by-day state AND daily messaging target follow Green API's
    stated sequence precisely (Day 2 authorize-only/COOLDOWN, Days 3–5 receiving-only ~every 2h,
    Day 6 replying begins, a 7-day 12→100 ramp, then GRADUATED);
  • the ~2h base cadence and the 12→100 ramp curve are reused unchanged (they already match GA);
  • a normal (non-recovery) enrollment's existing timeline is completely unchanged (regression).
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.warmup_state import WarmupState, RECOVERY_WARMUP_CONFIG
from app.services import warmup_scheduler as sch
from app.services.warmup_scheduler import (
    target_state_for_day, daily_target, day_index,
    RECOVERY_RECEIVING_DAYS, RECOVERY_REPLY_START_DAY, RECOVERY_GRADUATE_DAY, BASE_MU_MIN,
)

NOW = datetime(2026, 7, 22, 12, 0, 0)


def _enr(day, *, recovery=True, state=""):
    """An enrollment whose computed day_index == `day` (anchored on authorized_at)."""
    return SimpleNamespace(
        instance_id="7105325764",
        authorized_at=NOW - timedelta(days=day - 1) if day >= 1 else None,
        state=state, sent_today=0, received_today=0, recovery_mode=recovery,
    )


# ── the recovery-mode day-by-day state sequence (Green API's exact ladder) ────
def test_recovery_state_sequence_matches_green_api():
    # day_index 0–1 → COOLDOWN (GA Day 1 no-link + GA Day 2 authorize, send nothing)
    for day in (0, 1):
        assert target_state_for_day(day, "", recovery=True) == WarmupState.COOLDOWN.value
    # day_index 2,3,4 → RECEIVING (GA Days 3–5, receiving-only)
    for day in (2, 3, 4):
        assert target_state_for_day(day, "", recovery=True) == WarmupState.RECEIVING.value
    assert tuple(RECOVERY_RECEIVING_DAYS) == (2, 3, 4)
    # day_index 5 → REPLYING (GA Day 6, replies begin)
    assert RECOVERY_REPLY_START_DAY == 5
    assert target_state_for_day(5, "", recovery=True) == WarmupState.REPLYING.value
    # day_index 6–11 → RAMPING (GA Days 7–12, the 7-day 12→100 ramp)
    for day in range(6, RECOVERY_GRADUATE_DAY):
        assert target_state_for_day(day, "", recovery=True) == WarmupState.RAMPING.value
    # day_index >= 12 → GRADUATED
    assert RECOVERY_GRADUATE_DAY == 12
    for day in (12, 13, 20, 30):
        assert target_state_for_day(day, "", recovery=True) == WarmupState.GRADUATED.value


def test_recovery_daily_targets_match_green_api_ramp():
    # COOLDOWN days send nothing.
    assert daily_target(_enr(1), NOW) == 0
    # Receiving-only days: inbound cadence (~every 2h), no outbound ramp yet.
    assert daily_target(_enr(2), NOW) == 6
    assert daily_target(_enr(3), NOW) == 8
    assert daily_target(_enr(4), NOW) == 10
    # Replying begins day 5 at the bottom of the ramp (12), then ramps to 100 over 7 steps.
    expected_ramp = {5: 12, 6: 20, 7: 32, 8: 48, 9: 66, 10: 84, 11: 100}
    for day, tgt in expected_ramp.items():
        assert daily_target(_enr(day), NOW) == tgt, f"day {day}"
    # The full ramp is exactly Green API's 12→100.
    assert RECOVERY_WARMUP_CONFIG.ramp_curve[0] == 12
    assert RECOVERY_WARMUP_CONFIG.ramp_curve[-1] == 100
    # Graduated → warm-up sends nothing further (real campaigns govern it).
    assert daily_target(_enr(12), NOW) == 0


def test_recovery_reuses_two_hour_cadence():
    # Green API's ~2h receiving/replying cadence is the engine's existing base mean gap — reused.
    assert BASE_MU_MIN == 120


def test_recovery_graduation_is_conservative_relative_to_day_10():
    # Green API's headline "much more ban-resistant after ~10 days" milestone (GA Day 10 ≈
    # day_index 9) lands mid-ramp — still RAMPING, ~66/day, fully interactive. We only declare
    # GRADUATED after the whole 7-step ramp completes (day_index 12), which is stricter, not looser.
    assert target_state_for_day(9, "", recovery=True) == WarmupState.RAMPING.value
    assert daily_target(_enr(9), NOW) == 66


# ── recovery mode never overrides side states ────────────────────────────────
def test_recovery_side_states_are_sticky():
    for side in (WarmupState.PAUSED.value, WarmupState.YELLOWCARD.value,
                 WarmupState.BLOCKED_RESET.value):
        assert target_state_for_day(5, side, recovery=True) == side


# ── regression: the NON-recovery general timeline is completely unchanged ─────
def test_non_recovery_timeline_unchanged():
    # day 1 COOLDOWN, days 2–3 RECEIVING, day 4 REPLYING, days 5–10 RAMPING,
    # days 11–24 MATURING, day 25+ GRADUATED (the pre-V41 schedule, verbatim).
    assert target_state_for_day(1, "") == WarmupState.COOLDOWN.value
    assert target_state_for_day(2, "") == WarmupState.RECEIVING.value
    assert target_state_for_day(3, "") == WarmupState.RECEIVING.value
    assert target_state_for_day(4, "") == WarmupState.REPLYING.value
    for day in range(5, 11):
        assert target_state_for_day(day, "") == WarmupState.RAMPING.value
    for day in range(11, 25):
        assert target_state_for_day(day, "") == WarmupState.MATURING.value
    assert target_state_for_day(25, "") == WarmupState.GRADUATED.value


def test_non_recovery_daily_targets_unchanged():
    # A non-recovery enrollment: receiving days 2–3 (6,8), reply day 4 (12), ramp 5–10.
    assert daily_target(_enr(1, recovery=False), NOW) == 0
    assert daily_target(_enr(2, recovery=False), NOW) == 6
    assert daily_target(_enr(3, recovery=False), NOW) == 8
    assert daily_target(_enr(4, recovery=False), NOW) == 12   # REPLYING at ramp[0]
    assert daily_target(_enr(10, recovery=False), NOW) == 100
    # Day 4 differs by mode: RECEIVING (recovery) vs REPLYING (general) — the core divergence.
    assert target_state_for_day(4, "", recovery=True) == WarmupState.RECEIVING.value
    assert target_state_for_day(4, "", recovery=False) == WarmupState.REPLYING.value


def test_recovery_flag_defaults_off():
    # An enrollment double without the attribute (older callers) is treated as non-recovery.
    assert sch.recovery_enabled(SimpleNamespace()) is False
    assert sch.recovery_enabled(SimpleNamespace(recovery_mode=False)) is False
    assert sch.recovery_enabled(SimpleNamespace(recovery_mode=True)) is True
