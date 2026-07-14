"""V14 PART F — safety governors & yellowCard response tests (these protect the business)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from app.services import governors


def _acct(**kw):
    base = dict(status="active", computed_daily_limit=100, throttle_factor=1.0,
                throttle_until=None, cooldown_until=None, days_active=30)
    base.update(kw)
    ns = SimpleNamespace(**base)
    # computed_daily_limit is a property on the real model; here it's a plain attr
    return ns


# ── 200/day hard cap ────────────────────────────────────────────────────────
def test_daily_hard_cap_200():
    a = _acct(computed_daily_limit=500)
    assert governors.effective_daily_cap(a) == 200


def test_effective_cap_under_200_passthrough():
    a = _acct(computed_daily_limit=80)
    assert governors.effective_daily_cap(a) == 80


# ── throttle 0.5 ────────────────────────────────────────────────────────────
def test_throttle_halves_cap():
    a = _acct(computed_daily_limit=100, throttle_factor=0.5,
              throttle_until=datetime.utcnow() + timedelta(days=1))
    assert governors.is_throttled(a) is True
    assert governors.effective_daily_cap(a) == 50


def test_expired_throttle_ignored():
    a = _acct(computed_daily_limit=100, throttle_factor=0.5,
              throttle_until=datetime.utcnow() - timedelta(hours=1))
    assert governors.is_throttled(a) is False
    assert governors.effective_daily_cap(a) == 100


# ── cooldown ────────────────────────────────────────────────────────────────
def test_in_cooldown_true_and_unavailable():
    a = _acct(cooldown_until=datetime.utcnow() + timedelta(days=2))
    assert governors.in_cooldown(a) is True
    assert governors.account_available(a) is False   # resume/use blocked during cooldown


def test_cooldown_elapsed_available_again():
    a = _acct(cooldown_until=datetime.utcnow() - timedelta(minutes=1))
    assert governors.in_cooldown(a) is False
    assert governors.account_available(a) is True


# ── delay floor ─────────────────────────────────────────────────────────────
def test_delay_floor_500ms():
    assert governors.clamp_delay_ms(100) == 500
    assert governors.clamp_delay_ms(9000) == 9000
    assert governors.clamp_delay_ms("bad") == governors.DEFAULT_DELAY_MS


# ── 10-day warm-up ──────────────────────────────────────────────────────────
def test_warmup_is_ten_days():
    assert governors.WARMUP_DAYS == 10
    assert governors.WARMUP_NEW_CONTACTS_PER_DAY == 20


def test_computed_daily_limit_warmup_10_days():
    """The real Account model must hard-cap sends to 5/day for the first 10 days."""
    from app.models.account import Account
    a = Account(name="x", instance_id="1", api_token="t", days_active=9, max_daily_absolute=200,
                received_yesterday=100, quick_replies_yesterday=20)
    assert a.computed_daily_limit == 5           # day 9 still in warm-up
    a.days_active = 10
    assert a.computed_daily_limit > 5            # warm-up over


# ── auto-failover default OFF ───────────────────────────────────────────────
def test_auto_failover_defaults_off():
    from app.config import settings
    assert settings.auto_failover_on_yellow_card is False


# ── incident constants (the automatic response contract) ────────────────────
def test_incident_handler_constants():
    from app.services import incident_handler as ih
    assert ih.COOLDOWN_DAYS == 3
    assert ih.THROTTLE_DAYS == 7
    assert governors.YELLOW_THROTTLE_FACTOR == 0.5
