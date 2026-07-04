"""Tests for campaign-related logic: daily limit formula, phone normalization, rate limiter."""
import pytest
from app.models.account import Account
from app.services.excel_service import normalize_phone
from app.services.rate_limiter import DEFAULT_SCHEDULE


def _make_account(days_active=0, received_yesterday=0, quick_replies_yesterday=0):
    acc = Account(name="t", instance_id="x", api_token="y")
    acc.days_active = days_active
    acc.received_yesterday = received_yesterday
    acc.quick_replies_yesterday = quick_replies_yesterday
    return acc


def test_computed_daily_limit_baseline():
    acc = _make_account(days_active=0, received_yesterday=0, quick_replies_yesterday=0)
    assert acc.computed_daily_limit == 0


def test_computed_daily_limit_caps():
    # base capped at 10, incoming capped at 20, replies capped at 50
    acc = _make_account(days_active=99, received_yesterday=99, quick_replies_yesterday=99)
    assert acc.computed_daily_limit == 10 + 20 + 50


def test_computed_daily_limit_mixed():
    # Past the warm-up week (days_active >= 7) the full formula applies.
    acc = _make_account(days_active=8, received_yesterday=8, quick_replies_yesterday=2)
    # min(8,10)=8 + 8 + min(2*5, 50)=10 => 26
    assert acc.computed_daily_limit == 26


def test_computed_daily_limit_warmup_week_cap():
    # During week 1 (days_active < 7) the limit is hard-capped at 5,
    # even when the formula would allow far more.
    acc = _make_account(days_active=5, received_yesterday=20, quick_replies_yesterday=10)
    assert acc.computed_daily_limit == 5


def test_computed_daily_limit_cap_overrides_configured_floor():
    # A configured daily_limit floor does NOT bypass the week-1 cap.
    acc = _make_account(days_active=3)
    acc.daily_limit = 50
    assert acc.computed_daily_limit == 5
    # …but once warm-up completes, the floor applies again.
    acc.days_active = 7
    assert acc.computed_daily_limit == 50


@pytest.mark.parametrize("raw,expected", [
    ("09123456789", "989123456789"),
    ("9123456789", "989123456789"),
    ("989123456789", "989123456789"),
    ("12345", None),
    ("", None),
    (None, None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_rate_limit_schedule_is_ascending():
    hours = [s["hour_start"] for s in DEFAULT_SCHEDULE]
    assert hours == sorted(hours)
