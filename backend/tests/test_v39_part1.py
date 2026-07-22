"""V39 PART 1 — the UNIVERSAL 24h connect/reconnect cooldown, folded into the ONE shared gate.

Proves:
  • the pure check `connect_cooldown_active`: a just-(re)connected account is blocked for exactly
    24h (exclusive boundary), a NULL anchor is grandfathered (never blocking), and the generalized
    `connected_at` is preferred over the legacy `reconnected_at` (fallback when connected_at unset);
  • `can_send_now` now returns `(False, "connect_cooldown")` for a just-connected account — the check
    lives in ONE place (the shared V27 gate), so mesh, campaigns AND Team Collaboration all inherit it;
  • all THREE send paths (mesh `execute_action`, campaign `_deliver_message`, TC `_send_from_main`)
    refuse a just-connected sender WITHOUT hitting Green API, and let a >24h / grandfathered sender send;
  • the SAME behavior on a brand-new account's FIRST-EVER connection and on a later reconnection
    (identical field, identical gate) — plus the boundary becomes eligible exactly at +24h.
"""
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import send_gate
from app.services.send_gate import (
    can_send_now, gate_check, connect_cooldown_active, hours_until_connect_cooldown_over,
    clear_live_cache, CONNECT_COOLDOWN_HOURS,
)
from app.services.warmup_engine import execute_action

NOW = datetime(2026, 7, 22, 12, 0, 0)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_live_cache()
    yield
    clear_live_cache()


def _acct(instance_id="A", status="active", connected_at=None, reconnected_at=None,
          cooldown_until=None, throttle_until=None, throttle_factor=1.0,
          api_token="t", phone="989120000001", name="نام"):
    return SimpleNamespace(instance_id=instance_id, status=status,
                           connected_at=connected_at, reconnected_at=reconnected_at,
                           cooldown_until=cooldown_until, throttle_until=throttle_until,
                           throttle_factor=throttle_factor, api_token=api_token,
                           phone=phone, name=name)


# ── pure check ────────────────────────────────────────────────────────────────
def test_default_window_is_24h():
    assert CONNECT_COOLDOWN_HOURS == 24


def test_just_connected_is_blocked():
    assert connect_cooldown_active(_acct(connected_at=NOW), NOW) is True
    assert hours_until_connect_cooldown_over(_acct(connected_at=NOW), NOW) == pytest.approx(24.0)


def test_within_window_blocked():
    a = _acct(connected_at=NOW - timedelta(hours=23))
    assert connect_cooldown_active(a, NOW) is True
    assert hours_until_connect_cooldown_over(a, NOW) == pytest.approx(1.0)


def test_boundary_exclusive_at_exactly_24h():
    a = _acct(connected_at=NOW - timedelta(hours=24))
    assert connect_cooldown_active(a, NOW) is False
    assert hours_until_connect_cooldown_over(a, NOW) == 0.0


def test_after_window_not_blocked():
    a = _acct(connected_at=NOW - timedelta(hours=24, seconds=1))
    assert connect_cooldown_active(a, NOW) is False


def test_null_anchor_is_grandfathered():
    """GUARDRAIL 3: a pre-existing account with NO connect anchor must NOT be blocked."""
    assert connect_cooldown_active(_acct(connected_at=None, reconnected_at=None), NOW) is False
    assert hours_until_connect_cooldown_over(_acct(), NOW) == 0.0


def test_missing_attribute_is_safe():
    """A light double that doesn't model the anchor at all → not blocked."""
    assert connect_cooldown_active(SimpleNamespace(instance_id="X"), NOW) is False


def test_connected_at_preferred_reconnected_at_fallback():
    # connected_at wins when both present.
    both = _acct(connected_at=NOW - timedelta(hours=25), reconnected_at=NOW)
    assert connect_cooldown_active(both, NOW) is False       # connected_at (25h) → elapsed
    # legacy rows with only reconnected_at still honor their remaining cooldown.
    legacy = _acct(connected_at=None, reconnected_at=NOW - timedelta(hours=1))
    assert connect_cooldown_active(legacy, NOW) is True


# ── folded into the ONE shared gate ──────────────────────────────────────────
def test_can_send_now_blocks_just_connected():
    ok, reason = can_send_now(_acct(connected_at=NOW), live_state="authorized", now=NOW)
    assert ok is False and reason == "connect_cooldown"


def test_can_send_now_allows_grandfathered_and_aged():
    assert can_send_now(_acct(connected_at=None), live_state="authorized", now=NOW) == (True, "ok")
    aged = _acct(connected_at=NOW - timedelta(hours=25))
    assert can_send_now(aged, live_state="authorized", now=NOW) == (True, "ok")


def test_first_connection_and_reconnection_behave_identically():
    """Same field, same gate: a brand-new account's first-ever connection is blocked exactly like
    a reconnection, and both clear at +24h."""
    first = _acct(instance_id="FIRST", connected_at=NOW)                 # never connected before
    recon = _acct(instance_id="RECON", connected_at=NOW,
                  reconnected_at=NOW - timedelta(days=5))                # reconnected today
    assert can_send_now(first, now=NOW)[1] == "connect_cooldown"
    assert can_send_now(recon, now=NOW)[1] == "connect_cooldown"
    at_boundary = NOW + timedelta(hours=24)
    assert can_send_now(first, now=at_boundary) == (True, "ok")
    assert can_send_now(recon, now=at_boundary) == (True, "ok")


# ── mesh path (execute_action threads `now`) ─────────────────────────────────
class _RecClient:
    def __init__(self, calls, instance_id):
        self.calls, self.instance_id = calls, instance_id
    async def send_typing_ms(self, phone, typing_time_ms, typing_type=None):
        self.calls.append(("typing", self.instance_id)); return True
    async def send_message(self, phone, message):
        self.calls.append(("send", self.instance_id, phone)); return "MID"


class _FakeDB:
    def __init__(self): self.added = []
    def add(self, x): self.added.append(x)


def _edge():
    return SimpleNamespace(new_instance_id="NEW", peer_instance_id="PEER", msg_count=0,
                           last_msg_at=None, id=None, handshake_state="active",
                           saved_as_contact_new=True, saved_as_contact_peer=True)


def _enr(**kw):
    base = dict(id=None, instance_id="NEW", state="RECEIVING", sent_today=0, received_today=0,
                next_action_at=None, reply_ratio=0.0, last_activity_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_mesh_send_blocked_when_peer_just_connected(monkeypatch):
    async def _fast(_): return None
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", _fast)
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    new = _acct(instance_id="NEW")
    peer = _acct(instance_id="PEER", connected_at=NOW)           # peer (the sender for inbound) just connected
    action = {"action": "send", "direction": "inbound", "edge": _edge(), "next_action_at": NOW}
    out = await execute_action(_FakeDB(), action, _enr(), new, peer, client_factory=factory,
                               now=NOW, rng=random.Random(0))
    assert out.get("skipped") is True and out["reason"] == "connect_cooldown"
    assert not any(c[0] == "send" for c in calls)               # NO Green API send


@pytest.mark.asyncio
async def test_mesh_grandfathered_peer_still_sends(monkeypatch):
    async def _fast(_): return None
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", _fast)
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    action = {"action": "send", "direction": "inbound", "edge": _edge(), "next_action_at": NOW}
    out = await execute_action(_FakeDB(), action, _enr(), _acct(instance_id="NEW"),
                               _acct(instance_id="PEER", connected_at=None),
                               client_factory=factory, now=NOW, rng=random.Random(0))
    assert out.get("skipped") is not True
    assert any(c[0] == "send" and c[1] == "PEER" for c in calls)


# ── campaign path (gate_check uses real utcnow → use utcnow-relative anchors) ──
@pytest.mark.asyncio
async def test_campaign_deliver_refuses_just_connected_account():
    from app.services import campaign_runner
    from app.models.campaign import MessageStatus

    class _DB:
        def __init__(self): self.committed = 0
        def add(self, x): pass
        async def commit(self): self.committed += 1

    sent = []

    class _Client:
        def __init__(self, *a, **k): pass
        async def send_message(self, *a, **k): sent.append(a); return "MID"
    campaign_runner.GreenAPIClient = _Client
    cc = SimpleNamespace(status=None, error_message=None)
    account = _acct(instance_id="C", connected_at=datetime.utcnow())    # just connected
    out = await campaign_runner._deliver_message(_DB(), SimpleNamespace(), cc,
                                                 SimpleNamespace(phone="x"), account, [], [], [])
    assert cc.status == MessageStatus.pending
    assert "connect_cooldown" in (cc.error_message or "")
    assert sent == []


# ── Team Collaboration path (_send_from_main uses real utcnow) ────────────────
def _tc_factory(counter):
    from unittest.mock import AsyncMock, MagicMock
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
async def test_tc_send_blocked_when_sender_just_connected(monkeypatch):
    from app.services import warmup_helper_engine as he
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep",
                        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock())
    sender = _acct("TC-NEW", connected_at=datetime.utcnow())
    calls = {"n": 0}
    mid = await he._send_from_main(sender, "989120000001", "سلام", _tc_factory(calls))
    assert mid is None and calls["n"] == 0


@pytest.mark.asyncio
async def test_tc_send_allowed_when_sender_grandfathered(monkeypatch):
    from app.services import warmup_helper_engine as he
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep",
                        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock())
    sender = _acct("TC-OLD", connected_at=None, reconnected_at=None)
    calls = {"n": 0}
    mid = await he._send_from_main(sender, "989120000002", "سلام", _tc_factory(calls))
    assert mid == "MID" and calls["n"] == 1


@pytest.mark.asyncio
async def test_tc_send_allowed_after_24h(monkeypatch):
    from app.services import warmup_helper_engine as he
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep",
                        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock())
    sender = _acct("TC-AGED", connected_at=datetime.utcnow() - timedelta(hours=25))
    calls = {"n": 0}
    mid = await he._send_from_main(sender, "989120000003", "سلام", _tc_factory(calls))
    assert mid == "MID" and calls["n"] == 1
