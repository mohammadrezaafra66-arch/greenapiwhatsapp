"""V17 PART 4 — automatic jittered AI mesh scheduler.

With Green API mocked and time simulated, asserts:
  • No two numbers fire on the same minute; no number exceeds 2 msgs/min or 6 active h/day;
    nothing fires outside active hours (defers instead).
  • Daily targets track the ramp_curve (12→100); reply_ratio stays >= 0.50.
  • Intervals are randomized (variance present; not constant).
  • AI path yields non-duplicate messages; the fallback activates on AI failure and is also
    non-duplicate; the hardcoded pool works with an empty DB.
  • A number only ever messages a peer whose mutual-contact handshake is complete.
"""
import asyncio
import random
import statistics
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
import pytz

from app.services import warmup_scheduler as sch
from app.services.warmup_scheduler import (
    in_active_hours, next_active_start, next_gap_minutes, mu_for_target,
    schedule_next_action, day_index, target_state_for_day, ramp_daily_target,
    receiving_inbound_target, maturing_daily_target, daily_target, allowed_outbound,
    can_send_now, circadian_multiplier, weekend_multiplier, HARD_MIN_GAP_SECONDS,
)
from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG as CFG
from app.services import warmup_content as content
from app.services.warmup_content import (
    FALLBACK_PHRASES, assemble_fallback_message, generate_mesh_message,
    is_near_duplicate, content_hash,
)
from app.services import warmup_engine as engine
from app.services.warmup_engine import plan_number_action, messageable_edges, execute_action
from app.services.warmup_mesh_service import edge_is_messageable

TEHRAN = pytz.timezone("Asia/Tehran")


def _t(y=2026, mo=5, d=1, h=12, mi=0):
    return TEHRAN.localize(datetime(y, mo, d, h, mi, 0))


def _edge(new="NEW", peer="PEER", active=True):
    e = SimpleNamespace(new_instance_id=new, peer_instance_id=peer, msg_count=0,
                        last_msg_at=None, id=None)
    e.saved_as_contact_new = active
    e.saved_as_contact_peer = active
    e.handshake_state = "active" if active else "none"
    return e


def _enr(**kw):
    base = dict(id=None, instance_id="NEW", state="REPLYING", sent_today=0, received_today=0,
                authorized_at=datetime(2026, 4, 25, 9, 0, 0), started_at=datetime(2026, 4, 25, 9, 0, 0),
                next_action_at=None, reply_ratio=0.0, last_activity_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


# ════════════════════════════ active hours ════════════════════════════
def test_in_active_hours():
    assert in_active_hours(_t(h=10)) is True
    assert in_active_hours(_t(h=20)) is True
    assert in_active_hours(_t(h=8)) is False       # before 09:00
    assert in_active_hours(_t(h=22)) is False       # after 21:00


def test_next_active_start_defers_out_of_window():
    nxt = next_active_start(_t(h=23), rng=random.Random(1))
    assert nxt.date() == _t(h=23).date() + timedelta(days=1)  # next day
    assert 9 <= nxt.hour <= 9 or (nxt.hour == 9)               # ~09:xx (+jitter <40min)
    assert nxt.hour == 9


def test_scheduled_action_never_lands_outside_active_hours():
    r = random.Random(3)
    for h in (10, 14, 18, 20):
        for _ in range(50):
            nxt = schedule_next_action(_t(h=h), daily_target=40, rng=r)
            assert in_active_hours(nxt), f"scheduled outside window from hour {h}: {nxt}"


# ════════════════════════════ jittered intervals ════════════════════════════
def test_gap_is_randomized_not_constant():
    r = random.Random(5)
    gaps = [next_gap_minutes(rng=r) for _ in range(200)]
    assert min(gaps) >= 45 and max(gaps) <= 210       # clamp bounds
    assert statistics.pstdev(gaps) > 5                 # genuine variance, not a constant


def test_mu_shrinks_as_target_grows():
    assert mu_for_target(12) > mu_for_target(100)       # more volume → smaller mean gap
    assert mu_for_target(100) >= sch.GAP_MIN_FLOOR_MIN   # never below the hard floor


def test_two_numbers_do_not_fire_same_minute():
    """Each number draws its OWN jittered next_action_at → not synchronized. Distinct at
    second resolution, and genuinely spread out (not all clustered on one instant)."""
    base = _t(h=12)
    stamps = [schedule_next_action(base, 20, rng=random.Random(seed)) for seed in range(20)]
    distinct = {s.replace(microsecond=0) for s in stamps}
    assert len(distinct) == 20                            # all distinct at 1s resolution
    offsets = [(s - base).total_seconds() / 60.0 for s in stamps]
    assert statistics.pstdev(offsets) > 2                 # spread, not synchronized


def test_circadian_and_weekend_multipliers():
    assert circadian_multiplier(13) > circadian_multiplier(9)     # midday faster than morning
    assert circadian_multiplier(3) < circadian_multiplier(13)     # night slow
    assert weekend_multiplier(_t(2026, 5, 1)) == 0.5              # 2026-05-01 is a Friday
    assert weekend_multiplier(_t(2026, 5, 4)) == 1.0             # Monday full


# ════════════════════════════ 2/min + 6h/day caps ════════════════════════════
def test_can_send_now_enforces_two_per_minute():
    now = _t(h=12)
    assert can_send_now(now, last_send_at=now - timedelta(seconds=HARD_MIN_GAP_SECONDS + 1),
                        active_seconds_today=0) is True
    assert can_send_now(now, last_send_at=now - timedelta(seconds=10),
                        active_seconds_today=0) is False          # < 30s → blocked (2/min)


def test_can_send_now_enforces_daily_active_hours():
    now = _t(h=12)
    over = CFG.max_active_hours_per_day * 3600
    assert can_send_now(now, None, active_seconds_today=over) is False
    assert can_send_now(now, None, active_seconds_today=over - 60) is True


# ════════════════════════════ day-by-day targets ════════════════════════════
def test_state_progression_by_day():
    assert target_state_for_day(1, "COOLDOWN") == "COOLDOWN"
    assert target_state_for_day(2, "COOLDOWN") == "RECEIVING"
    assert target_state_for_day(3, "RECEIVING") == "RECEIVING"
    assert target_state_for_day(4, "RECEIVING") == "REPLYING"
    assert target_state_for_day(7, "REPLYING") == "RAMPING"
    assert target_state_for_day(15, "RAMPING") == "MATURING"
    assert target_state_for_day(26, "MATURING") == "GRADUATED"


def test_side_states_are_sticky():
    for s in ("PAUSED", "YELLOWCARD", "BLOCKED_RESET"):
        assert target_state_for_day(8, s) == s       # scheduler never overrides a side state


def test_ramp_targets_track_curve_12_to_100():
    got = [ramp_daily_target(d) for d in range(4, 11)]   # days 4..10
    assert got == [12, 20, 32, 48, 66, 84, 100] == CFG.ramp_curve
    assert got[0] == 12 and got[-1] == 100
    # smooth ramp — no day more than doubles the previous (no spikes)
    for a, b in zip(got, got[1:]):
        assert a < b <= 2 * a


def test_receiving_inbound_targets():
    assert receiving_inbound_target(2) == 6
    assert receiving_inbound_target(3) == 8
    assert receiving_inbound_target(4) == 10


def test_maturing_band_80_to_120():
    r = random.Random(9)
    vals = [maturing_daily_target(r) for _ in range(200)]
    assert all(80 <= v <= 120 for v in vals)
    assert len(set(vals)) > 1                             # natural variation, not constant


# ════════════════════════════ reply-ratio guard ════════════════════════════
def test_allowed_outbound_keeps_ratio_at_least_half():
    # With `received` inbound, sending up to allowed_outbound keeps received/sent >= 0.5.
    for received in (2, 5, 10, 40):
        cap = allowed_outbound(received, 0.5)
        assert received / cap >= 0.5 - 1e-9
    assert allowed_outbound(0, 0.5) >= 1                  # can always start replying


def test_plan_respects_ratio_switches_to_inbound():
    # Already sent as many as allowed for its inbound count → next turn must be inbound.
    enr = _enr(state="RAMPING", received_today=4, sent_today=8)  # allowed_outbound(4)=8
    plan = plan_number_action(enr, [_edge()], _t(h=12), CFG, random.Random(0))
    assert plan["action"] == "send" and plan["direction"] == "inbound"


def test_plan_allows_outbound_when_ratio_healthy():
    enr = _enr(state="RAMPING", received_today=10, sent_today=2)
    plan = plan_number_action(enr, [_edge()], _t(h=12), CFG, random.Random(0))
    assert plan["action"] == "send" and plan["direction"] == "outbound"


# ════════════════════════════ plan gating ════════════════════════════
def test_plan_cooldown_day_one():
    enr = _enr(state="COOLDOWN", authorized_at=datetime(2026, 5, 1, 8, 0, 0),
               started_at=datetime(2026, 5, 1, 8, 0, 0))
    plan = plan_number_action(enr, [_edge()], _t(h=12), CFG, random.Random(0))
    assert plan["action"] == "cooldown"


def test_plan_defers_outside_active_hours():
    enr = _enr(state="REPLYING")
    plan = plan_number_action(enr, [_edge()], _t(h=23), CFG, random.Random(0))
    assert plan["action"] == "defer" and in_active_hours(plan["next_action_at"])


def test_plan_waits_until_next_action_at():
    enr = _enr(state="REPLYING", next_action_at=_t(h=14))
    plan = plan_number_action(enr, [_edge()], _t(h=12), CFG, random.Random(0))
    assert plan["action"] == "wait"


def test_plan_target_reached():
    # anchor 3 days before "now" → day 4 (REPLYING), whose ramp target is 12.
    day4_anchor = datetime(2026, 4, 28, 9, 0, 0)
    enr = _enr(state="REPLYING", sent_today=6, received_today=6,
               authorized_at=day4_anchor, started_at=day4_anchor)
    assert day_index(enr, _t(h=12)) == 4 and ramp_daily_target(4) == 12
    plan = plan_number_action(enr, [_edge()], _t(h=12), CFG, random.Random(0))
    assert plan["action"] == "target_reached"


def test_plan_never_messages_stranger():
    """Only messageable (mutual-contact) edges are ever selected — never a stranger."""
    only_incomplete = [_edge(active=False), _edge(active=False)]
    plan = plan_number_action(_enr(), only_incomplete, _t(h=12), CFG, random.Random(0))
    assert plan["action"] == "no_peers"
    # mixed: the plan must pick the messageable one
    mixed = [_edge(peer="P_bad", active=False), _edge(peer="P_good", active=True)]
    plan2 = plan_number_action(_enr(), mixed, _t(h=12), CFG, random.Random(0))
    assert plan2["action"] == "send"
    assert edge_is_messageable(plan2["edge"]) and plan2["edge"].peer_instance_id == "P_good"


def test_messageable_edges_filter():
    edges = [_edge(active=True), _edge(active=False), _edge(active=True)]
    assert len(messageable_edges(edges)) == 2


# ════════════════════════════ content: pool + anti-repeat ════════════════════════════
def test_fallback_pool_is_large_hardcoded_and_unique():
    assert len(FALLBACK_PHRASES) >= 500            # spec: large pool (>=500)
    assert len(set(FALLBACK_PHRASES)) == len(FALLBACK_PHRASES)
    assert all(p and p.strip() for p in FALLBACK_PHRASES)


def test_fallback_works_with_empty_db_and_is_non_repeating():
    """The hardcoded constant needs no DB. Across many draws for one edge, tracking used
    hashes yields non-repeating output."""
    r = random.Random(11)
    used, msgs = set(), []
    for _ in range(200):
        m = assemble_fallback_message(recent_hashes=used, name="علی", rng=r)
        used.add(content_hash(m))
        msgs.append(m)
    # No exact repeats among 200 tracked draws.
    assert len(set(msgs)) == len(msgs)


def test_near_duplicate_detection():
    assert is_near_duplicate("سلام وقت بخیر", ["سلام وقت بخیر!"]) is True     # punctuation only
    assert is_near_duplicate("قیمت یخچال چنده", ["حال شما خوبه؟"]) is False


@pytest.mark.asyncio
async def test_generate_uses_ai_then_rejects_duplicates():
    async def ai_fn(**kw):
        return "پیام هوش مصنوعی تازه و منحصر به فرد"
    text, source = await generate_mesh_message(ai_fn=ai_fn, rng=random.Random(1))
    assert source == "ai" and text.strip()

    # If the AI keeps returning a near-duplicate of history, it must fall back.
    async def dup_ai(**kw):
        return "سلام وقت بخیر"
    text2, source2 = await generate_mesh_message(
        ai_fn=dup_ai, history=["سلام وقت بخیر"], rng=random.Random(1))
    assert source2 == "fallback"


@pytest.mark.asyncio
async def test_generate_falls_back_when_ai_raises():
    async def boom(**kw):
        raise RuntimeError("AI over budget")
    text, source = await generate_mesh_message(ai_fn=boom, rng=random.Random(2))
    assert source == "fallback" and text.strip()


# ════════════════════════════ execute_action (mock Green API) ════════════════════════════
class _FakeDB:
    def __init__(self): self.added = []
    def add(self, x): self.added.append(x)


class _RecClient:
    def __init__(self, calls, instance_id):
        self.calls, self.instance_id = calls, instance_id
    async def send_typing_ms(self, phone, typing_time_ms, typing_type=None):
        self.calls.append(("typing", self.instance_id, phone)); return True
    async def send_message(self, phone, message):
        self.calls.append(("send", self.instance_id, phone, message)); return "MID"


@pytest.mark.asyncio
async def test_execute_outbound_sends_from_new_to_peer_and_updates_ratio(monkeypatch):
    async def _fast(_): return None
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", _fast)
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    new = SimpleNamespace(instance_id="NEW", api_token="t", phone="989120000001", name="نو")
    peer = SimpleNamespace(instance_id="PEER", api_token="t", phone="989120000002", name="پیر")
    enr = _enr(state="RAMPING", sent_today=0, received_today=4)
    edge = _edge()
    action = {"action": "send", "direction": "outbound", "edge": edge,
              "next_action_at": _t(h=13), "target": 40}
    db = _FakeDB()
    out = await execute_action(db, action, enr, new, peer, client_factory=factory,
                               now=_t(h=12), rng=random.Random(0))
    # sent from NEW to the PEER's phone
    sends = [c for c in calls if c[0] == "send"]
    assert sends and sends[0][1] == "NEW" and sends[0][2] == "989120000002"
    assert enr.sent_today == 1
    assert enr.reply_ratio == 4 / 1                      # received/sent
    assert edge.msg_count == 1
    assert out["direction"] == "outbound" and out["message_id"] == "MID"
    # an event log row was written
    from app.models.warmup_mesh import WarmupEventLog
    assert any(isinstance(x, WarmupEventLog) for x in db.added)


@pytest.mark.asyncio
async def test_execute_inbound_sends_from_peer_to_new(monkeypatch):
    async def _fast(_): return None
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", _fast)
    calls = []
    factory = lambda iid, tok: _RecClient(calls, iid)
    new = SimpleNamespace(instance_id="NEW", api_token="t", phone="989120000001", name="نو")
    peer = SimpleNamespace(instance_id="PEER", api_token="t", phone="989120000002", name="پیر")
    enr = _enr(state="RECEIVING", sent_today=0, received_today=0)
    action = {"action": "send", "direction": "inbound", "edge": _edge(),
              "next_action_at": _t(h=13)}
    out = await execute_action(_FakeDB(), action, enr, new, peer, client_factory=factory,
                               now=_t(h=12), rng=random.Random(0))
    sends = [c for c in calls if c[0] == "send"]
    assert sends[0][1] == "PEER" and sends[0][2] == "989120000001"   # peer → new
    assert enr.received_today == 1 and out["direction"] == "inbound"
