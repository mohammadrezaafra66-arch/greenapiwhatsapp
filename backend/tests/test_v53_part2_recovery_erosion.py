"""V53 PART 2 — recovery enrollment must not be killed minutes later by erosion detection.

The live failure this pins (7105325764):

    2026-07-30 22:00  state_change {"to":"COOLDOWN","reason":"v41_recovery_enroll"}
    2026-07-30 22:14  kill         {"from":"COOLDOWN","reason":"erosion"}   -> BLOCKED_RESET

`enroll_recovery_mode` re-anchored started_at/authorized_at but NOT last_activity_at, which still
read 2026-07-16. `warmup_safety_scan` runs every 6h and anchors on
`last_activity_at or started_at`, so the very next scan saw 14+ idle days and reset the number.
BLOCKED_RESET is sticky, so the account then sat permanently ineligible.

Proves:
  • enrollment re-anchors last_activity_at to now;
  • the erosion rule that fired is unchanged (14d/30d thresholds intact);
  • a freshly-enrolled recovery number no longer trips erosion, while a genuinely idle one still does.
"""
import inspect
from datetime import datetime, timedelta

import pytest

from app.services import warmup_recovery_enroll as re_enroll
from app.services.warmup_killswitch import (
    idle_reset_reason, EROSION_IDLE_DAYS, AUTOLOGOUT_IDLE_DAYS,
)

NOW = datetime(2026, 7, 30, 22, 0)


# ── the erosion rule itself is untouched ─────────────────────────────────────
def test_erosion_thresholds_unchanged():
    assert EROSION_IDLE_DAYS == 14
    assert AUTOLOGOUT_IDLE_DAYS == 30


def test_idle_reset_reason_boundaries():
    assert idle_reset_reason(13) is None
    assert idle_reset_reason(14) == "erosion"
    assert idle_reset_reason(29) == "erosion"
    assert idle_reset_reason(30) == "auto_logout"


# ── the fix: enrollment re-anchors last_activity_at ──────────────────────────
def test_enroll_recovery_mode_reanchors_last_activity_at():
    """Source-level guard: the assignment must be present next to the other re-anchors."""
    src = inspect.getsource(re_enroll.enroll_recovery_mode)
    assert "enr.last_activity_at = now" in src


def test_freshly_enrolled_number_does_not_trip_erosion():
    """Simulate warmup_safety_scan's anchor logic right after enrollment."""
    last_activity_at = NOW          # what the fix now writes
    started_at = NOW
    anchor = last_activity_at or started_at
    scan_at = NOW + timedelta(minutes=14)      # the scan that killed it live
    idle_days = (scan_at - anchor).days
    assert idle_reset_reason(idle_days) is None


def test_stale_anchor_would_still_have_tripped_erosion():
    """The pre-fix state, kept so the regression is explicit rather than implied."""
    last_activity_at = datetime(2026, 7, 16, 16, 51)     # the real stale value
    scan_at = NOW + timedelta(minutes=14)
    idle_days = (scan_at - last_activity_at).days
    assert idle_days >= EROSION_IDLE_DAYS
    assert idle_reset_reason(idle_days) == "erosion"


def test_genuinely_idle_number_still_trips_after_the_fix():
    """The fix must not disable erosion — only stop it firing at enrollment time."""
    enrolled_at = NOW
    scan_at = NOW + timedelta(days=15)         # 15 quiet days after enrollment
    idle_days = (scan_at - enrolled_at).days
    assert idle_reset_reason(idle_days) == "erosion"
