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
    # Day 0 is inside the warm-up week → capped at 5 (Meta-standard, V8 F39).
    acc = _make_account(days_active=0, received_yesterday=0, quick_replies_yesterday=0)
    assert acc.computed_daily_limit == 5


def test_computed_daily_limit_caps():
    # Past week 1: base capped at 10, incoming (×0.5, cap 20), replies capped at 50.
    acc = _make_account(days_active=99, received_yesterday=99, quick_replies_yesterday=99)
    # base=10 + min(int(99*0.5),20)=20 + min(99*5,50)=50 = 80 (under absolute cap 200)
    assert acc.computed_daily_limit == 80


def test_computed_daily_limit_mixed():
    # Past the warm-up week (days_active >= 7) the full formula applies.
    acc = _make_account(days_active=8, received_yesterday=8, quick_replies_yesterday=2)
    # min(8,10)=8 + min(int(8*0.5),20)=4 + min(2*5,50)=10 => 22
    assert acc.computed_daily_limit == 22


def test_computed_daily_limit_warmup_week_cap():
    # During week 1 (days_active < 7) the limit is hard-capped at 5,
    # even when the formula would allow far more.
    acc = _make_account(days_active=5, received_yesterday=20, quick_replies_yesterday=10)
    assert acc.computed_daily_limit == 5


def test_computed_daily_limit_respects_absolute_cap():
    # max_daily_absolute is the hard ceiling past week 1.
    acc = _make_account(days_active=30, received_yesterday=40, quick_replies_yesterday=10)
    acc.max_daily_absolute = 30  # base=10 + incoming=20 + replies=50 = 80, capped to 30
    assert acc.computed_daily_limit == 30


def test_computed_daily_limit_no_longer_uses_daily_limit_floor():
    # V8 F39 removed the daily_limit floor; only the formula + absolute cap apply.
    acc = _make_account(days_active=7)
    acc.daily_limit = 50  # no effect anymore
    # base=7 + incoming=0 + replies=0 = 7
    assert acc.computed_daily_limit == 7


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
