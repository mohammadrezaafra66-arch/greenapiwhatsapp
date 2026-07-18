"""V27 PART 7 — volume-spike guard for all sending instances.

Proves:
  • a graduated/established instance with a big campaign after a QUIET week is smoothed/ramped
    (capped) rather than sent all at once;
  • a small first batch on a previously-unused (avg 0) number is NOT blocked (the floor);
  • an instance already sending high volume is not falsely capped;
  • the guard never allows MORE than the account's own hard cap;
  • the async trailing-average + guarded-cap wrappers read daily_send_logs correctly.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import volume_guard as vg
from app.services.volume_guard import (
    spike_capped_volume, is_spike, trailing_daily_average, guarded_daily_cap,
    SPIKE_MULTIPLIER, MIN_DAILY_FLOOR,
)

NOW = datetime(2026, 7, 18, 12, 0, 0)


# ── pure math ────────────────────────────────────────────────────────────────
def test_quiet_week_big_campaign_is_smoothed():
    # trailing avg ~0 sends/day, hard cap 500 → allowed clamps to the floor, not 500
    assert spike_capped_volume(0.0, 500) == MIN_DAILY_FLOOR
    assert spike_capped_volume(0.0, 500) < 500


def test_small_first_batch_not_blocked_by_floor():
    # a warmed but previously-unused number sending 15 today: floor(20) >= 15 → allowed
    allowed = spike_capped_volume(0.0, 200)
    assert allowed >= 15 and is_spike(15, 0.0) is False


def test_established_high_volume_not_falsely_capped():
    # steady ~50/day for a week → 4x = 200, hard cap 200 → full cap, no false smoothing
    assert spike_capped_volume(50.0, 200) == 200
    assert is_spike(60, 50.0) is False           # 60 <= 200 → normal


def test_big_jump_is_a_spike():
    assert is_spike(300, 10.0) is True           # 300 > max(20, 40)
    assert spike_capped_volume(10.0, 500) == max(MIN_DAILY_FLOOR, int(10 * SPIKE_MULTIPLIER))


def test_never_exceeds_hard_cap():
    assert spike_capped_volume(1000.0, 30) == 30  # spike cap huge but hard cap wins


# ── async wrappers ───────────────────────────────────────────────────────────
class _Result:
    def __init__(self, scalar): self._scalar = scalar
    def scalar(self): return self._scalar


class _DB:
    def __init__(self, count): self._count = count
    async def execute(self, *a, **k): return _Result(self._count)


@pytest.mark.asyncio
async def test_trailing_average_divides_by_days():
    db = _DB(70)                    # 70 sends over the 7-day window
    avg = await trailing_daily_average(db, "acc-id", NOW, days=7)
    assert avg == 10.0


def _acct(days_active=30, sent_today=0):
    return SimpleNamespace(id="acc-id", instance_id="I", days_active=days_active,
                           sent_today=sent_today, received_yesterday=0, quick_replies_yesterday=0,
                           max_daily_absolute=200, incoming_ratio_multiplier=0.5,
                           throttle_factor=1.0, throttle_until=None, cooldown_until=None,
                           computed_daily_limit=200)


@pytest.mark.asyncio
async def test_guarded_cap_smooths_after_quiet_week():
    db = _DB(0)                     # nothing sent in the last 7 days
    res = await guarded_daily_cap(db, _acct(), NOW)
    assert res["allowed"] == MIN_DAILY_FLOOR and res["smoothed"] is True


@pytest.mark.asyncio
async def test_guarded_cap_not_smoothed_for_active_number():
    db = _DB(350)                  # 50/day avg → 4x = 200 == hard cap
    res = await guarded_daily_cap(db, _acct(), NOW)
    assert res["smoothed"] is False and res["allowed"] == res["hard_cap"]
