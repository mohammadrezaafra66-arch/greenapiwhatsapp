"""V38 — mandatory 24h post-RECONNECT rest for the Team-Collaboration send path.

Proves:
  • the pure gate: no rest owed when never reconnected; rest active within 24h of a reconnect;
    rest cleared after 24h; the window is configurable and consistent with the 24h post-auth rule;
  • the integration: `_send_from_main` (the single choke point for EVERY TC send) refuses a
    just-reconnected sender WITHOUT hitting Green API, and lets a long-recovered sender send;
  • backward-compat: an account with no `reconnected_at` (every existing row) is unaffected;
  • isolation: the rest is a NEW TC-path check — it never consults or mutates the shared V27
    send_gate/can_send_now, so other accounts' campaign/mesh gates are untouched.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_engine as he
from app.services import send_gate
from app.services.warmup_reconnect_rest import (
    reconnect_rest_active, hours_until_rest_over, RECONNECT_REST_HOURS,
)

NOW = datetime(2026, 7, 22, 12, 0, 0)


@pytest.fixture(autouse=True)
def _reset():
    send_gate.clear_live_cache()
    yield
    send_gate.clear_live_cache()


def _acc(iid="SENDER", reconnected_at=None, cooldown_until=None, throttle_until=None):
    return SimpleNamespace(instance_id=iid, api_token="t", phone="9890", name=iid,
                           is_warm_peer=False, status=SimpleNamespace(value="active"),
                           reconnected_at=reconnected_at,
                           cooldown_until=cooldown_until, throttle_until=throttle_until,
                           throttle_factor=1.0)


# ── pure gate ────────────────────────────────────────────────────────────────
def test_no_rest_when_never_reconnected():
    acc = _acc(reconnected_at=None)
    assert reconnect_rest_active(acc, NOW) is False
    assert hours_until_rest_over(acc, NOW) == 0.0


def test_missing_attribute_is_safe():
    """An object that simply doesn't model reconnected_at (e.g. a light test double) → no rest."""
    assert reconnect_rest_active(SimpleNamespace(instance_id="X"), NOW) is False


def test_rest_active_right_after_reconnect():
    acc = _acc(reconnected_at=NOW)
    assert reconnect_rest_active(acc, NOW) is True
    assert hours_until_rest_over(acc, NOW) == pytest.approx(24.0)


def test_rest_active_at_23h():
    acc = _acc(reconnected_at=NOW - timedelta(hours=23))
    assert reconnect_rest_active(acc, NOW) is True
    assert hours_until_rest_over(acc, NOW) == pytest.approx(1.0)


def test_rest_cleared_just_after_24h():
    acc = _acc(reconnected_at=NOW - timedelta(hours=24, seconds=1))
    assert reconnect_rest_active(acc, NOW) is False
    assert hours_until_rest_over(acc, NOW) == 0.0


def test_rest_boundary_is_exclusive_at_exactly_24h():
    """At exactly +24h the rest is over (now < ra+24h is False)."""
    acc = _acc(reconnected_at=NOW - timedelta(hours=24))
    assert reconnect_rest_active(acc, NOW) is False


def test_window_is_configurable():
    acc = _acc(reconnected_at=NOW - timedelta(hours=10))
    assert reconnect_rest_active(acc, NOW, hours=6) is False   # 6h window already elapsed
    assert reconnect_rest_active(acc, NOW, hours=24) is True   # 24h window still active
    assert RECONNECT_REST_HOURS == 24                          # matches the project's 24h rule


# ── integration: the single TC send choke point ──────────────────────────────
def _send_factory(counter):
    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t):
            counter["n"] += 1
            return "MID"
        c.send_message = AsyncMock(side_effect=_s)
        return c
    return factory


@pytest.mark.asyncio
async def test_send_blocked_during_post_reconnect_rest(monkeypatch):
    """A sender that reconnected 1h ago is refused by _send_from_main with NO Green API send."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("SENDER-R", reconnected_at=datetime.utcnow() - timedelta(hours=1))
    calls = {"n": 0}
    mid = await he._send_from_main(sender, "989120000001", "سلام", _send_factory(calls))
    assert mid is None and calls["n"] == 0


@pytest.mark.asyncio
async def test_send_allowed_after_rest_elapsed(monkeypatch):
    """The SAME sender, reconnected 25h ago, sends normally (rest cleared, health gate passes)."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("SENDER-R2", reconnected_at=datetime.utcnow() - timedelta(hours=25))
    calls = {"n": 0}
    mid = await he._send_from_main(sender, "989120000002", "سلام", _send_factory(calls))
    assert mid == "MID" and calls["n"] == 1


@pytest.mark.asyncio
async def test_send_allowed_when_never_reconnected(monkeypatch):
    """Backward-compat: an account with reconnected_at=None (every existing row) is unaffected."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("SENDER-OLD", reconnected_at=None)
    calls = {"n": 0}
    mid = await he._send_from_main(sender, "989120000003", "سلام", _send_factory(calls))
    assert mid == "MID" and calls["n"] == 1


@pytest.mark.asyncio
async def test_rest_does_not_touch_shared_v27_gate(monkeypatch):
    """The rest must be a SEPARATE check: can_send_now (the shared gate) never sees reconnected_at,
    so a carded OTHER account's gate behavior is identical whether or not this feature exists."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    # can_send_now has no notion of reconnected_at → a just-reconnected but otherwise-healthy
    # account is still "allowed" by the V27 gate itself; only the TC-path wrapper blocks it.
    sender = _acc("SENDER-ISO", reconnected_at=datetime.utcnow())
    allowed, reason = send_gate.can_send_now(sender, None, datetime.utcnow())
    assert allowed is True and reason == "ok"          # V27 gate is unchanged
    assert reconnect_rest_active(sender) is True         # the NEW TC-only gate is what blocks
