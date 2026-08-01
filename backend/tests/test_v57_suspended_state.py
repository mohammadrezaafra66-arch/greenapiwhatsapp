"""V57 — `suspended` must block sending, and its expiry must be stored.

Two real gaps, both hit on 2026-08-01 by instance 770022695753 (989048249540):

  1. `suspended` — Green API's spam-restriction state — was in NONE of BLOCKING_LIVE_STATES,
     KILL_LIVE_STATES or DANGER_STATES. The gate did not refuse a suspended instance and the
     state monitor did not quarantine it. That number only stopped sending because an unrelated
     `notAuthorized` webhook happened to move its status off `active` seconds earlier; without
     that coincidence the system would have kept sending from a restricted number.

  2. `getWaSettings.suspendedUntil` — the ONE fact separating a temporary restriction from a
     permanent block — was never read or stored. The live value was 1786199855 = 2026-08-08
     14:37:35 UTC, exactly 7 days, and the only way to see it was to call the API by hand.

Proves the gate refuses `suspended`, the monitor treats it as danger, the epoch parses (and
garbage does not), and the value is set while suspended and cleared the moment it is not.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import send_gate
from app.services.send_gate import (
    BLOCKING_LIVE_STATES, KILL_LIVE_STATES, can_send_now,
)
from app.services import state_monitor
from app.services.state_monitor import DANGER_STATES, parse_suspended_until

NOW = datetime(2026, 8, 1, 15, 0)
LIVE_EPOCH = 1786199855          # the real suspendedUntil observed on 770022695753


def _acc(status="active", connected_at=None, suspended_until=None):
    return SimpleNamespace(instance_id="C1", status=status, api_token="t",
                           connected_at=connected_at or (NOW - timedelta(days=30)),
                           reconnected_at=None, suspended_until=suspended_until,
                           throttle_factor=1.0, throttle_until=None,
                           cooldown_until=None, last_incident_at=None)


# ── the state sets ──────────────────────────────────────────────────────────
def test_suspended_is_in_every_dangerous_set():
    assert "suspended" in BLOCKING_LIVE_STATES
    assert "suspended" in KILL_LIVE_STATES
    assert "suspended" in DANGER_STATES


def test_gate_refuses_a_suspended_instance():
    allowed, reason = can_send_now(_acc(), "suspended", NOW)
    assert allowed is False
    assert reason == "live_state:suspended"


def test_gate_still_allows_a_healthy_authorized_instance():
    allowed, reason = can_send_now(_acc(), "authorized", NOW)
    assert allowed is True and reason == "ok"


def test_previously_blocking_states_still_block():
    for s in ("yellowcard", "blocked", "notauthorized", "starting"):
        allowed, reason = can_send_now(_acc(), s, NOW)
        assert allowed is False, f"{s} must still block"


# ── parsing the epoch ───────────────────────────────────────────────────────
def test_parse_the_real_observed_value():
    got = parse_suspended_until({"suspendedUntil": LIVE_EPOCH})
    assert got == datetime(2026, 8, 8, 14, 37, 35)


def test_parse_accepts_a_numeric_string():
    assert parse_suspended_until({"suspendedUntil": str(LIVE_EPOCH)}) == \
        datetime(2026, 8, 8, 14, 37, 35)


@pytest.mark.parametrize("payload", [
    {}, None, {"suspendedUntil": None}, {"suspendedUntil": 0}, {"suspendedUntil": "0"},
    {"suspendedUntil": ""}, {"suspendedUntil": "nope"}, {"suspendedUntil": []},
])
def test_parse_returns_none_for_anything_unusable(payload):
    assert parse_suspended_until(payload) is None


# ── the value tracks the live state ─────────────────────────────────────────
class _FakeClient:
    def __init__(self, payload):
        self.payload = payload

    async def get_wa_settings(self):
        return self.payload


class _FakeDB:
    def add(self, *_a, **_k):
        pass


@pytest.mark.asyncio
async def test_refresh_stores_the_expiry(monkeypatch):
    acc = _acc()
    got = await state_monitor.refresh_suspended_until(
        _FakeDB(), acc, client=_FakeClient({"suspendedUntil": LIVE_EPOCH}))
    assert got == datetime(2026, 8, 8, 14, 37, 35)
    assert acc.suspended_until == datetime(2026, 8, 8, 14, 37, 35)


@pytest.mark.asyncio
async def test_refresh_survives_an_api_failure():
    """Best-effort by contract — a lookup failure must not break the poll/webhook path."""
    class _Boom:
        async def get_wa_settings(self):
            raise RuntimeError("network down")

    acc = _acc(suspended_until=datetime(2026, 8, 8))
    assert await state_monitor.refresh_suspended_until(_FakeDB(), acc, client=_Boom()) is None


@pytest.mark.asyncio
async def test_apply_state_clears_the_expiry_once_no_longer_suspended(monkeypatch):
    """A stale «آزاد می‌شود» date in the UI would be worse than none at all."""
    async def _noop_persist(*_a, **_k):
        return None

    monkeypatch.setattr(send_gate, "persist_live_state", _noop_persist)
    acc = _acc(suspended_until=datetime(2026, 8, 8, 14, 37, 35))
    await state_monitor.apply_state(_FakeDB(), acc, "authorized", "poll", NOW)
    assert acc.suspended_until is None


@pytest.mark.asyncio
async def test_apply_state_quarantines_a_suspended_instance(monkeypatch):
    async def _noop_persist(*_a, **_k):
        return None

    async def _fake_refresh(_db, account, client=None):
        account.suspended_until = datetime(2026, 8, 8, 14, 37, 35)
        return account.suspended_until

    monkeypatch.setattr(send_gate, "persist_live_state", _noop_persist)
    monkeypatch.setattr(state_monitor, "refresh_suspended_until", _fake_refresh)
    acc = _acc()
    res = await state_monitor.apply_state(_FakeDB(), acc, "suspended", "webhook", NOW)

    assert res["acted"] == "suspended"                 # quarantined, not silently recorded
    assert acc.suspended_until == datetime(2026, 8, 8, 14, 37, 35)
    assert acc.cooldown_until is not None and acc.throttle_until is not None
