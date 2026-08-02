"""V64 — the campaign form and accounts-overview must report the SAME age.

The live contradiction: accounts-overview showed «۱۸.۲ روز» for instance 770022683809 while the
campaign form showed «۵», which was read as five days. Both numbers were real and they measured
different things:

  • 18.2  — `peer_age_days()`, i.e. now - connected_since(); the age accounts-overview renders
  • 5     — `computed_daily_limit`, i.e. MESSAGES PER DAY, driven by the `days_active` warm-up
            counter, which only advances while `warmup_enabled` is true and therefore sat at 0

Nothing on the campaign form said which quantity its number was. So `GET /accounts/` now serves
the overview's own age alongside the cap, from the same function, and these tests pin two things:

  1. the age field is literally the overview's calculation (not a re-implementation), and
  2. the age NEVER feeds a cap — an account that has existed 18 days but never sent a message is
     untested, not warmed up, and must keep the 5/day brake.
"""
from datetime import datetime, timedelta

import pytest

from app.api.v1 import accounts as accounts_api
from app.models.account import Account
from app.services import warmup_peer_eligibility as pe

NOW = datetime(2026, 8, 2, 16, 0)


def _account(**kw):
    a = Account()
    a.instance_id = kw.pop("instance_id", "770022683809")
    a.created_at = kw.pop("created_at", datetime(2026, 7, 15, 11, 23))
    a.partner_created_at = kw.pop("partner_created_at", None)
    a.connected_at = kw.pop("connected_at", None)
    a.days_active = kw.pop("days_active", 0)
    a.max_daily_absolute = kw.pop("max_daily_absolute", 200)
    a.received_yesterday = kw.pop("received_yesterday", 0)
    a.quick_replies_yesterday = kw.pop("quick_replies_yesterday", 0)
    a.incoming_ratio_multiplier = kw.pop("incoming_ratio_multiplier", 0.5)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


# ── the two numbers are genuinely different quantities ──────────────────────
def test_the_real_account_reproduces_both_numbers():
    """The exact row that triggered the report: 18.2 days old, capped at 5 messages."""
    a = _account()
    assert round(pe.peer_age_days(a, None, NOW), 1) == 18.2
    assert a.computed_daily_limit == 5           # messages/day — NOT days


def test_days_active_is_a_counter_not_an_age():
    """18 days of real elapsed time, counter still 0 — that is the whole contradiction."""
    a = _account(days_active=0)
    assert pe.peer_age_days(a, None, NOW) > 18
    assert a.days_active == 0


# ── the endpoint serves the overview's own calculation ──────────────────────
def test_the_endpoint_imports_the_overview_age_function():
    """A re-implementation would drift; the two pages must call the SAME function."""
    import inspect
    src = inspect.getsource(accounts_api.list_accounts)
    assert "peer_age_days" in src
    assert "connected_since" in src


def test_the_endpoint_exposes_age_and_the_anchor_it_is_measured_from():
    import inspect
    src = inspect.getsource(accounts_api.list_accounts)
    for field in ("age_days", "age_anchor_at", "connected_at", "ever_sent"):
        assert f'"{field}"' in src, f"{field} must be served so the form need not guess"


def test_age_is_measured_from_the_same_anchor_the_overview_uses():
    a = _account()
    assert pe.connected_since(a, None) == a.created_at


def test_partner_created_at_wins_when_it_is_earlier():
    """connected_since takes the EARLIEST trustworthy timestamp."""
    earlier = datetime(2026, 7, 15, 11, 0)
    a = _account(partner_created_at=earlier)
    assert pe.connected_since(a, None) == earlier


# ── the brake is untouched ──────────────────────────────────────────────────
def test_the_age_never_raises_the_cap():
    """The hazard of "just use the overview's age": at 18 days the `days < 10` guard would stop
    applying and these accounts would jump from 5/day to 30/day — on numbers that have never sent
    a single message, and whose batch-mate was suspended one second after its first one."""
    a = _account(days_active=0, received_yesterday=1926)
    assert pe.peer_age_days(a, None, NOW) > 14      # old by the overview's measure
    assert a.computed_daily_limit == 5              # still capped, because the counter is 0


def test_the_cap_still_follows_the_counter_only():
    for counter, expected in ((0, 5), (9, 5), (10, 10)):
        a = _account(days_active=counter)
        assert a.computed_daily_limit == expected


def test_a_very_old_row_with_a_zero_counter_is_still_capped():
    a = _account(created_at=datetime(2020, 1, 1), days_active=0)
    assert pe.peer_age_days(a, None, NOW) > 2000
    assert a.computed_daily_limit == 5


# ── age must never be fabricated ────────────────────────────────────────────
def test_an_account_with_no_timestamps_has_no_age():
    a = _account(created_at=None)
    assert pe.connected_since(a, None) is None
    assert pe.peer_age_days(a, None, NOW) is None


def test_connected_at_is_reported_separately_from_the_age():
    """`connected_at` NULL is the fact that matters: these instances were never recorded
    connecting to Green API, so the age is row age, not connection age."""
    a = _account(connected_at=None)
    assert a.connected_at is None
    assert pe.peer_age_days(a, None, NOW) is not None   # an age exists, but not from a connection


@pytest.mark.parametrize("days,expected_ge", [(1, 1), (14, 14), (18, 18)])
def test_age_tracks_elapsed_time(days, expected_ge):
    a = _account(created_at=NOW - timedelta(days=days))
    assert pe.peer_age_days(a, None, NOW) >= expected_ge - 0.01
