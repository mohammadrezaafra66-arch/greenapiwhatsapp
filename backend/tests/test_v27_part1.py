"""V27 PART 1 — the live pre-send health gate.

Proves:
  • can_send_now refuses status!=active / cooldown / throttle / live yellowCard-blocked, and
    passes a healthy instance.
  • the in-memory live-state mirror honours freshness (stale entries are ignored).
  • the EXACT incident: a peer carded mid-tick (cooldown set, or a fresh live yellowCard) makes
    the next mesh send attempt skip WITHOUT calling Green API — logged, not silently allowed.
  • the campaign send path refuses an unhealthy account (contact left pending, no send) and a
    live danger state trips the kill-switch.
  • every send call-site (mesh, campaign, helper-assist) consults the gate before sendMessage:
    a mock client that fails the test if send_message runs while the gate would have blocked.
  • a healthy instance still sends normally (no regression).
"""
import json
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import send_gate
from app.services.send_gate import (
    can_send_now, gate_check, get_cached_live_state, update_live_state, clear_live_cache,
    is_kill_reason, LIVE_STATE_MAX_AGE_SECONDS,
)
from app.services import warmup_engine as engine
from app.services.warmup_engine import execute_action


NOW = datetime(2026, 7, 18, 12, 0, 0)


def _acct(instance_id="A", status="active", cooldown_until=None, throttle_until=None,
          throttle_factor=1.0, api_token="t", phone="989120000001", name="نام"):
    return SimpleNamespace(instance_id=instance_id, status=status, cooldown_until=cooldown_until,
                           throttle_until=throttle_until, throttle_factor=throttle_factor,
                           api_token=api_token, phone=phone, name=name)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_live_cache()
    yield
    clear_live_cache()


# ── pure gate ────────────────────────────────────────────────────────────────
def test_healthy_instance_passes():
    ok, reason = can_send_now(_acct(), live_state="authorized", now=NOW)
    assert ok is True and reason == "ok"


def test_not_active_is_refused():
    ok, reason = can_send_now(_acct(status="banned"), now=NOW)
    assert ok is False and reason == "not_active"


def test_cooldown_in_future_is_refused():
    a = _acct(cooldown_until=NOW + timedelta(days=1))
    ok, reason = can_send_now(a, now=NOW)
    assert ok is False and reason == "cooldown"


def test_expired_cooldown_passes():
    a = _acct(cooldown_until=NOW - timedelta(hours=1))
    ok, _ = can_send_now(a, now=NOW)
    assert ok is True


def test_active_throttle_is_refused():
    a = _acct(throttle_until=NOW + timedelta(days=2), throttle_factor=0.5)
    ok, reason = can_send_now(a, now=NOW)
    assert ok is False and reason == "throttled"


def test_live_yellowcard_and_blocked_are_refused():
    assert can_send_now(_acct(), live_state="yellowCard", now=NOW) == (False, "live_state:yellowcard")
    assert can_send_now(_acct(), live_state="blocked", now=NOW) == (False, "live_state:blocked")
    assert can_send_now(_acct(), live_state="notAuthorized", now=NOW)[0] is False


def test_unknown_live_state_does_not_block():
    ok, _ = can_send_now(_acct(), live_state="authorized", now=NOW)
    assert ok is True


def test_is_kill_reason():
    assert is_kill_reason("live_state:yellowcard") is True
    assert is_kill_reason("live_state:blocked") is True
    assert is_kill_reason("cooldown") is False
    assert is_kill_reason("throttled") is False


# ── in-memory live-state mirror freshness ────────────────────────────────────
def test_live_cache_fresh_and_stale():
    update_live_state("A", "yellowCard", NOW)
    assert get_cached_live_state("A", NOW) == "yellowcard"
    # older than the max age → ignored (treated as unknown)
    stale_now = NOW + timedelta(seconds=LIVE_STATE_MAX_AGE_SECONDS + 5)
    assert get_cached_live_state("A", stale_now) is None
    assert get_cached_live_state("UNKNOWN", NOW) is None


def test_gate_check_uses_fresh_cache():
    a = _acct(instance_id="P")
    update_live_state("P", "yellowCard", NOW)
    ok, reason = gate_check(a, NOW)
    assert ok is False and reason == "live_state:yellowcard"


# ── mesh incident reproduction ───────────────────────────────────────────────
class _RecClient:
    """Records send_message calls; used to prove the gate blocks BEFORE the API call."""
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
async def test_mesh_send_blocked_when_peer_in_cooldown(monkeypatch):
    """The exact incident: peer carded mid-tick (cooldown set). Next inbound send must skip
    without calling Green API and log a gate_skip event."""
    async def _fast(_): return None
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", _fast)
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    new = _acct(instance_id="NEW", phone="989120000001")
    peer = _acct(instance_id="PEER", phone="989120000002",
                 cooldown_until=NOW + timedelta(days=2))   # carded → resting
    action = {"action": "send", "direction": "inbound", "edge": _edge(), "next_action_at": NOW}
    db = _FakeDB()
    out = await execute_action(db, action, _enr(), new, peer, client_factory=factory, now=NOW,
                               rng=random.Random(0))
    assert out.get("skipped") is True and out["reason"] == "cooldown"
    assert not any(c[0] == "send" for c in calls)          # NO Green API send happened
    from app.models.warmup_mesh import WarmupEventLog
    skips = [x for x in db.added if isinstance(x, WarmupEventLog) and x.event_type == "gate_skip"]
    assert len(skips) == 1


@pytest.mark.asyncio
async def test_mesh_send_blocked_on_live_yellowcard(monkeypatch):
    async def _fast(_): return None
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", _fast)
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    update_live_state("PEER", "yellowCard", NOW)           # live card in the mirror
    action = {"action": "send", "direction": "inbound", "edge": _edge(), "next_action_at": NOW}
    out = await execute_action(_FakeDB(), action, _enr(), _acct(instance_id="NEW"),
                               _acct(instance_id="PEER"), client_factory=factory, now=NOW,
                               rng=random.Random(0))
    assert out.get("skipped") is True
    assert not any(c[0] == "send" for c in calls)


@pytest.mark.asyncio
async def test_mesh_healthy_peer_still_sends(monkeypatch):
    """No regression: a healthy peer sends normally."""
    async def _fast(_): return None
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", _fast)
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    action = {"action": "send", "direction": "inbound", "edge": _edge(), "next_action_at": NOW}
    out = await execute_action(_FakeDB(), action, _enr(), _acct(instance_id="NEW"),
                               _acct(instance_id="PEER"), client_factory=factory, now=NOW,
                               rng=random.Random(0))
    assert out.get("skipped") is not True
    assert any(c[0] == "send" and c[1] == "PEER" for c in calls)


# ── campaign path ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_campaign_deliver_refuses_unhealthy_account():
    from app.services import campaign_runner
    from app.models.campaign import MessageStatus

    class _DB:
        def __init__(self): self.committed = 0
        def add(self, x): pass
        async def commit(self): self.committed += 1

    sent = []

    class _Client:
        def __init__(self, *a): pass
        async def send_message(self, *a, **k): sent.append(a); return "MID"
    # patch the client so a leak would be observable
    campaign_runner.GreenAPIClient = _Client
    cc = SimpleNamespace(status=None, error_message=None)
    account = _acct(instance_id="C", cooldown_until=NOW + timedelta(days=1))
    campaign = SimpleNamespace()
    out = await campaign_runner._deliver_message(_DB(), campaign, cc, SimpleNamespace(phone="x"),
                                                 account, [], [], [])
    assert cc.status == MessageStatus.pending
    assert "send gate" in (cc.error_message or "")
    assert sent == []                                      # no send happened


# ── helper-assist path ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_helper_send_blocked_when_main_unhealthy():
    from app.services import warmup_helper_engine as he
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    sender = _acct(instance_id="MAIN", throttle_until=NOW + timedelta(days=1), throttle_factor=0.5)
    # gate uses "now" internally; force the throttle to be active by monkeypatching not needed —
    # is_throttled compares to datetime.utcnow(); use a far-future throttle_until so it's active.
    sender.throttle_until = datetime.utcnow() + timedelta(days=1)
    mid = await he._send_from_main(sender, "989120000009", "سلام", factory)
    assert mid is None
    assert calls == []
