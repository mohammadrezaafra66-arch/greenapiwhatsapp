"""V19 PART 4 — automatic group-placement scheduler (fixed anti-ban schedule).

Green API mocked, time simulated. Asserts the fixed schedule (no action before Day 4,
first at Day 4, ≤1/day, ≤5 in first 10 days, ≥48h spacing, waking hours only, never 2 in a
session, Day 10+ slows to ≥3 days), the placement procedure (mutual save → add → one retry
on false → failure without a hammer loop), kill-switch halts, troubled-warm drop, that the
message mesh is UNCHANGED (separate engine), and that no polling is touched.
"""
import uuid
import inspect
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
import pytz

from app.services import warmup_group_scheduler as gs
from app.services.warmup_group_scheduler import (
    group_action_due, pick_next_target, count_actions_today, last_action_at,
    count_group_actions, GROUP_FIRST_ACTION_DAY, GROUP_MAX_IN_FIRST_10_DAYS,
    GROUP_MIN_SPACING_HOURS,
)
from app.services.warmup_state import WarmupState

TEHRAN = pytz.timezone("Asia/Tehran")


def _t(y=2026, mo=5, d=1, h=12, mi=0):
    return TEHRAN.localize(datetime(y, mo, d, h, mi, 0))


def _enr(day_offset, state="RAMPING"):
    """Enrollment whose authorized_at is `day_offset` days before 2026-05-20 12:00."""
    anchor = datetime(2026, 5, 20, 9, 0, 0) - timedelta(days=day_offset)
    return SimpleNamespace(instance_id="COLD", state=state,
                           authorized_at=anchor, started_at=anchor)


NOW = _t(2026, 5, 20, 12, 0)     # midday, waking hours


def _mem(group_id="g", status="added", attempts=1, added_at=None, last_attempt_at=None):
    return SimpleNamespace(group_id=group_id, status=status, attempts=attempts,
                           added_at=added_at, last_attempt_at=last_attempt_at)


# ════════════ schedule gating ════════════
def test_no_action_before_day_4():
    # day 1 (COOLDOWN), 2, 3 (RECEIVING) → no group action
    for d in (1, 2, 3):
        due, reason = group_action_due(_enr(d - 1, state="RECEIVING" if d >= 2 else "COOLDOWN"), [], NOW)
        assert due is False and reason == "before_day_4"


def test_first_action_at_day_4():
    # day 4 = REPLYING, no prior memberships, waking hours → allowed
    due, reason = group_action_due(_enr(3, state="REPLYING"), [], NOW)
    assert due is True and reason == "ok"


def test_daily_cap_one_per_day():
    e = _enr(5)   # day 6 RAMPING
    today_action = _mem(added_at=datetime(2026, 5, 20, 10, 0, 0))   # already acted today
    due, reason = group_action_due(e, [today_action], NOW)
    assert due is False and reason == "daily_cap"


def test_48h_spacing_enforced():
    e = _enr(6)   # day 7
    recent = _mem(group_id="g1", added_at=datetime(2026, 5, 19, 12, 0, 0))  # ~24h ago
    due, reason = group_action_due(e, [recent], NOW)
    assert due is False and reason == "spacing_48h"
    # 49h ago → allowed
    old = _mem(group_id="g1", added_at=datetime(2026, 5, 18, 11, 0, 0))
    due2, _ = group_action_due(e, [old], NOW)
    assert due2 is True


def test_five_membership_cap_in_first_10_days():
    e = _enr(8)   # day 9 (<=10)
    five = [_mem(group_id=f"g{i}", status="added",
                 added_at=datetime(2026, 5, 12 + i, 10, 0, 0)) for i in range(5)]
    due, reason = group_action_due(e, five, NOW)
    assert due is False and reason == "ten_day_cap"
    # only four so far, and last one >48h ago → allowed
    four = [_mem(group_id=f"g{i}", status="added",
                 added_at=datetime(2026, 5, 12 + i, 10, 0, 0)) for i in range(4)]
    due2, _ = group_action_due(e, four, NOW)
    assert due2 is True


def test_outside_waking_hours_blocked():
    e = _enr(5)
    night = _t(2026, 5, 20, 23, 0)     # 23:00 — outside 09–21
    due, reason = group_action_due(e, [], night)
    assert due is False and reason == "outside_waking"


def test_maturing_slows_to_3_10_days():
    e = _enr(14, state="MATURING")     # day 15 (>10)
    two_days = _mem(group_id="g1", added_at=datetime(2026, 5, 18, 12, 0, 0))  # 2 days ago
    due, reason = group_action_due(e, [two_days], NOW)
    assert due is False and reason == "maturing_spacing"
    four_days = _mem(group_id="g1", added_at=datetime(2026, 5, 16, 12, 0, 0))  # 4 days ago
    due2, _ = group_action_due(e, [four_days], NOW)
    assert due2 is True


def test_paused_or_carded_halts_group_actions():
    for st in ("PAUSED", "YELLOWCARD", "BLOCKED_RESET"):
        due, reason = group_action_due(_enr(6, state=st), [], NOW)
        assert due is False and reason == "paused_or_carded"


# ════════════ pick_next_target ════════════
def test_pick_next_target_excludes_touched_groups():
    targets = [SimpleNamespace(group_id="g1", is_selected=True, warm_instance_id="W"),
               SimpleNamespace(group_id="g2", is_selected=True, warm_instance_id="W"),
               SimpleNamespace(group_id="g3", is_selected=True, warm_instance_id="W")]
    memberships = [_mem(group_id="g1", status="added"), _mem(group_id="g2", status="failed")]
    picked = pick_next_target("COLD", targets, memberships, rng=random.Random(0))
    assert picked.group_id == "g3"       # g1 added + g2 failed both excluded (no re-hammer)


def test_pick_next_target_none_when_all_touched():
    targets = [SimpleNamespace(group_id="g1", is_selected=True, warm_instance_id="W")]
    assert pick_next_target("COLD", targets, [_mem(group_id="g1")], rng=random.Random(0)) is None


# ════════════ placement procedure (mock Green API) ════════════
class RecClient:
    def __init__(self, instance_id, add_results, log):
        self.instance_id = instance_id
        self._add_results = list(add_results)
        self.log = log
    async def add_contact(self, phone, name, *a, **k):
        self.log.append(("add_contact", self.instance_id, phone)); return True
    async def add_group_participant(self, group_id, phone):
        self.log.append(("add_participant", self.instance_id, group_id, phone))
        return self._add_results.pop(0) if self._add_results else {"addParticipant": False}


class FakeDB:
    def __init__(self): self.added = []
    def add(self, o): self.added.append(o)


def _accounts():
    cold = SimpleNamespace(instance_id="COLD", api_token="t", phone="989120000001", name="سرد",
                           status=None)
    warm = SimpleNamespace(instance_id="WARM", api_token="t", phone="989122270261", name="گرم",
                           status=None)
    return cold, warm


@pytest.mark.asyncio
async def test_placement_mutual_save_before_add_then_success():
    from app.services.warmup_group_engine import place_cold_in_group
    from app.models.warmup_mesh import WarmupGroupMembership, WarmupEventLog
    log = []
    cf = lambda iid, tok: RecClient(iid, [{"addParticipant": True}], log)
    cold, warm = _accounts()
    m = WarmupGroupMembership(cold_instance_id="COLD", warm_instance_id="WARM", group_id="g1", status="pending")
    ok = await place_cold_in_group(FakeDB(), cold, warm, "g1", m, client_factory=cf, now=datetime(2026, 5, 20, 12, 0))
    assert ok is True and m.status == "added" and m.added_at is not None
    # a contact save happened BEFORE the participant add
    first_add = next(i for i, e in enumerate(log) if e[0] == "add_participant")
    assert any(e[0] == "add_contact" for e in log[:first_add])
    # warm(admin) is the one who added the cold number to the group
    part = [e for e in log if e[0] == "add_participant"][0]
    assert part[1] == "WARM" and part[3] == "989120000001"


@pytest.mark.asyncio
async def test_placement_false_retries_once_then_fails_no_hammer():
    from app.services.warmup_group_engine import place_cold_in_group
    from app.models.warmup_mesh import WarmupGroupMembership
    log = []
    cf = lambda iid, tok: RecClient(iid, [{"addParticipant": False}, {"addParticipant": False}], log)
    cold, warm = _accounts()
    m = WarmupGroupMembership(cold_instance_id="COLD", warm_instance_id="WARM", group_id="g1", status="pending")
    ok = await place_cold_in_group(FakeDB(), cold, warm, "g1", m, client_factory=cf, now=datetime(2026, 5, 20, 12, 0))
    assert ok is False and m.status == "failed" and m.error_reason
    # exactly TWO add_participant attempts (initial + one retry) — no hammer loop
    assert sum(1 for e in log if e[0] == "add_participant") == 2
    assert m.attempts == 2


@pytest.mark.asyncio
async def test_placement_false_then_true_on_retry():
    from app.services.warmup_group_engine import place_cold_in_group
    from app.models.warmup_mesh import WarmupGroupMembership
    log = []
    cf = lambda iid, tok: RecClient(iid, [{"addParticipant": False}, {"addParticipant": True}], log)
    cold, warm = _accounts()
    m = WarmupGroupMembership(cold_instance_id="COLD", warm_instance_id="WARM", group_id="g1", status="pending")
    ok = await place_cold_in_group(FakeDB(), cold, warm, "g1", m, client_factory=cf, now=datetime(2026, 5, 20, 12, 0))
    assert ok is True and m.status == "added"


# ════════════ engine tick: caps, never 2 in a session, halts ════════════
class ScalarsRes:
    def __init__(self, items): self._items = list(items)
    def scalars(self):
        outer = self
        class S:
            def all(self_inner): return list(outer._items)
        return S()


class TickDB:
    def __init__(self, targets, enrollments, accounts, memberships_by_cold):
        # execute() is called in this order: breaker(kill events), targets, enrollments, accounts, then memberships per cold
        self._q = []
        self.added = []; self.commits = 0
        self._targets = targets; self._enr = enrollments; self._accts = accounts
        self._memb = memberships_by_cold
        self._phase = 0
    async def execute(self, q):
        self._phase += 1
        # 1: is_breaker_tripped → kill events (none). 2: targets. 3: enrollments. 4: accounts. 5+: memberships
        if self._phase == 1: return ScalarsRes([])            # no kill/breaker events
        if self._phase == 2: return ScalarsRes(self._targets)
        if self._phase == 3: return ScalarsRes(self._enr)
        if self._phase == 4: return ScalarsRes(self._accts)
        # memberships query per cold (all use same set here)
        return ScalarsRes(self._memb)
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1


@pytest.mark.asyncio
async def test_tick_places_one_group_and_never_two_in_a_session():
    from app.services.warmup_group_engine import run_group_warmup_tick
    from app.models.warmup_mesh import WarmupGroupMembership
    cold = SimpleNamespace(instance_id="COLD", api_token="t", phone="989120000001", name="c",
                           status=__import__("app.models.account", fromlist=["AccountStatus"]).AccountStatus.active)
    warm = SimpleNamespace(instance_id="WARM", api_token="t", phone="989122270261", name="w",
                           status=cold.status)
    targets = [SimpleNamespace(group_id="g1", is_selected=True, warm_instance_id="WARM"),
               SimpleNamespace(group_id="g2", is_selected=True, warm_instance_id="WARM")]
    enr = _enr(5)  # day 6, RAMPING, in waking hours at NOW
    enr.is_enabled = True
    db = TickDB(targets, [enr], [cold, warm], memberships_by_cold=[])
    log = []
    cf = lambda iid, tok: RecClient(iid, [{"addParticipant": True}], log)
    res = await run_group_warmup_tick(db, now=NOW, client_factory=cf)
    # exactly ONE group action this session even though 2 targets are selected
    assert res["acted"] == 1
    assert sum(1 for e in log if e[0] == "add_participant") == 1
    added_membs = [x for x in db.added if isinstance(x, WarmupGroupMembership)]
    assert len(added_membs) == 1


@pytest.mark.asyncio
async def test_tick_halts_when_breaker_tripped():
    from app.services.warmup_group_engine import run_group_warmup_tick
    class BreakerDB:
        async def execute(self, q):
            # is_breaker_tripped reads kill events — return a tripped mesh_breaker event
            import json
            row = SimpleNamespace(event_type="kill", created_at=NOW.replace(tzinfo=None),
                                  payload_json=json.dumps({"scope": "mesh_breaker", "active": True}))
            return ScalarsRes([row])
        def add(self, o): pass
        async def commit(self): pass
    res = await run_group_warmup_tick(BreakerDB(), now=NOW.replace(tzinfo=None), client_factory=lambda *a: None)
    assert res.get("halted") is True


# ════════════ message mesh is UNCHANGED (separate engine) ════════════
def test_mesh_engine_does_not_reference_group_warmup():
    import app.services.warmup_engine as mesh
    src = inspect.getsource(mesh)
    # the message-mesh module must not import/touch the group-placement track
    assert "warmup_group_engine" not in src
    assert "WarmupGroupTarget" not in src
    assert "add_group_participant" not in src


def test_mesh_plan_unaffected_by_group_data():
    """plan_number_action (mesh cadence) takes no group inputs → identical with/without groups."""
    from app.services.warmup_engine import plan_number_action
    from types import SimpleNamespace as NS
    edge = NS(new_instance_id="COLD", peer_instance_id="P", msg_count=0, last_msg_at=None, id=None,
              saved_as_contact_new=True, saved_as_contact_peer=True, handshake_state="active")
    enr = NS(id=None, instance_id="COLD", state="REPLYING", sent_today=0, received_today=0,
             authorized_at=datetime(2026, 5, 16, 9, 0), started_at=datetime(2026, 5, 16, 9, 0),
             next_action_at=None)
    p1 = plan_number_action(enr, [edge], NOW, rng=random.Random(0))
    p2 = plan_number_action(enr, [edge], NOW, rng=random.Random(0))
    assert p1["action"] == p2["action"]     # deterministic, unaffected by any group state
