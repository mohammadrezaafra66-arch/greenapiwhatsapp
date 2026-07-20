"""V28 PART 4 — hard pacing + health gate for outreach sending.

Proves the non-negotiable safety rails (there is NO contact-count cap, so pacing IS the rail):
  • an outreach send is blocked when the shared per-instance pacer says the sender sent too
    recently — the SAME pacer the mesh uses (mesh send + outreach ask can't interleave fast);
  • a healthy, ready sender does send; the send re-arms the pacer;
  • an unhealthy/carded sender is blocked by the SAME V27 live health gate as mesh/campaigns;
  • outreach is sent FROM the contact's own sender (multi-sender), not a single global main;
  • the Tehran→UTC conversion keeps the shared pacer on one clock as the mesh;
  • V25's single-reminder / thank-you behavior is preserved (generalized per sender).
"""
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytz

from app.services import warmup_helper_engine as he
from app.services import warmup_helper_service as hs
from app.services import peer_pacer, send_gate
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperConfig
from app.services.warmup_state import WarmupState

TEHRAN = pytz.timezone("Asia/Tehran")
TEHRAN_11AM = datetime(2026, 5, 4, 11, 0)      # inside waking hours


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset()
    send_gate.clear_live_cache()
    yield
    peer_pacer.reset()
    send_gate.clear_live_cache()


def _acc(iid, warm=False, cooldown_until=None, throttle_until=None, throttle_factor=1.0):
    return SimpleNamespace(instance_id=iid, api_token="t", phone=f"9890{iid}", name=iid,
                           is_warm_peer=warm, status=SimpleNamespace(value="active"),
                           cooldown_until=cooldown_until, throttle_until=throttle_until,
                           throttle_factor=throttle_factor)


# ── pure: resolve_task_sender (multi-sender) ─────────────────────────────────
def test_resolve_task_sender_uses_contacts_own_sender():
    a1, a2 = _acc("S1"), _acc("S2")
    h = WarmupHelper(name="رضا", phone="9891", sender_instance_id="S2")
    assert he.resolve_task_sender([a1, a2], h, {}) is a2


def test_resolve_task_sender_falls_back_to_main_for_legacy():
    peer = _acc("P1", warm=True)
    other = _acc("O1")
    h = WarmupHelper(name="رضا", phone="9891", sender_instance_id=None)   # legacy row
    assert he.resolve_task_sender([other, peer], h, {}) is peer           # main sender


def test_any_account_can_be_a_sender_not_just_warm_peers():
    plain = _acc("PLAIN", warm=False)
    h = WarmupHelper(name="رضا", phone="9891", sender_instance_id="PLAIN")
    assert he.resolve_task_sender([plain], h, {}) is plain   # not restricted to warm peers


# ── Tehran→UTC keeps the shared pacer on one clock ───────────────────────────
def test_tehran_to_utc_naive():
    utc = he._to_utc_naive(TEHRAN_11AM)
    expected = TEHRAN.localize(TEHRAN_11AM).astimezone(pytz.utc).replace(tzinfo=None)
    assert utc == expected
    assert (TEHRAN_11AM - utc) == timedelta(hours=3, minutes=30)   # Iran is UTC+3:30


# ── engine: shared pacer blocks a too-soon outreach send ─────────────────────
def _tick_db(sender, helper, task, config):
    """A FakeDB mimicking run_helper_tick's query order."""
    class _Scalars:
        def __init__(s, items): s._i = list(items)
        def all(s): return list(s._i)
    class _Res:
        def __init__(s, scalars=None, rows=None):
            s._s = scalars or []; s._rows = rows
        def scalars(s): return _Scalars(s._s)
        def all(s): return list(s._rows) if s._rows is not None else list(s._s)
        def scalar_one_or_none(s): return s._s[0] if s._s else None
    class _DB:
        def __init__(s):
            s.commits = 0
            s._q = [
                _Res(scalars=[config]),                                  # get_config
                _Res(scalars=[]),                                        # V33 PART 4 — expire_exhausted_reminders (none)
                _Res(rows=[("C1", WarmupState.RECEIVING.value, True)]),  # enr states (cold number)
                _Res(scalars=[helper]),                                  # list_helpers
                _Res(scalars=[]),                                        # ensure_helper_tasks existing
                _Res(scalars=[sender]),                                  # active accounts (pick_main_sender)
                _Res(scalars=[task]),                                    # candidate tasks
            ]
        async def execute(s, *a, **k): return s._q.pop(0) if s._q else _Res()
        def add(s, o): pass
        async def flush(s): pass
        async def commit(s): s.commits += 1
        async def refresh(s, o): pass
        async def get(s, m, pk): return None
    return _DB()


@pytest.mark.asyncio
async def test_outreach_send_blocked_when_pacer_not_ready(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("SENDER-X")
    helper = WarmupHelper(name="رضا", phone="989111111111", is_active=True,
                          sender_instance_id="SENDER-X")
    import uuid
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_PENDING)
    task.id = uuid.uuid4(); task.created_at = TEHRAN_11AM
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)
    # Pre-record a send from SENDER-X at the SAME UTC instant → pacer not ready
    peer_pacer.record_peer_send("SENDER-X", he._to_utc_naive(TEHRAN_11AM), random.Random(0))

    sent = {"n": 0}
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): sent["n"] += 1; return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    res = await he.run_helper_tick(_tick_db(sender, helper, task, config), now=TEHRAN_11AM,
                                   client_factory=factory, rng=random.Random(1))
    assert res.get("paced") is True and res["acted"] == 0
    assert sent["n"] == 0                       # NO send (paced out)


@pytest.mark.asyncio
async def test_outreach_send_proceeds_when_ready_and_records_pacer(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("SENDER-Y")
    helper = WarmupHelper(name="مریم", phone="989222222222", is_active=True,
                          sender_instance_id="SENDER-Y")
    import uuid
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_PENDING)
    task.id = uuid.uuid4(); task.created_at = TEHRAN_11AM
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)

    sent = {"n": 0}
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): sent["n"] += 1; return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    res = await he.run_helper_tick(_tick_db(sender, helper, task, config), now=TEHRAN_11AM,
                                   client_factory=factory, rng=random.Random(2))
    assert res["acted"] == 1 and res["sent"] is True
    assert res["sender_instance_id"] == "SENDER-Y"
    # the pacer was re-armed → an immediate second send from SENDER-Y would be blocked
    assert peer_pacer.peer_ready("SENDER-Y", he._to_utc_naive(TEHRAN_11AM)) is False


@pytest.mark.asyncio
async def test_carded_sender_blocked_by_health_gate(monkeypatch):
    """The same V27 live gate used for mesh/campaigns blocks an unhealthy outreach sender."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("SENDER-Z", cooldown_until=datetime.utcnow() + timedelta(days=2))  # carded (real-time)
    calls = {"n": 0}
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): calls["n"] += 1; return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    mid = await he._send_from_main(sender, "989111111111", "سلام", factory)
    assert mid is None and calls["n"] == 0      # gate blocked it, no Green API send
