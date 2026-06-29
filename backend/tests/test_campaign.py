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
    acc = _make_account(days_active=5, received_yesterday=8, quick_replies_yesterday=2)
    # 5 + 8 + min(2*5, 50)=10 => 23
    assert acc.computed_daily_limit == 23


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
