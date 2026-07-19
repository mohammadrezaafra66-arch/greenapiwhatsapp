"""V29 PART 7 «همکاری تیمی» — per-cold-account enrollment + the automatic 10-day cycle.

Proves:
  • the pure schedule math: day-index by Tehran date, the conservative ramp (day 0–1 → 1/day,
    day 2–9 → 2/day, past 10 days → 0), no two steps on one thread per day, thread selection;
  • a cold account WITHIN its 24h post-auth cooldown gets NO ask-send;
  • after the cooldown clears, a step is sent (gated/paced) and the thread advances;
  • a thread already stepped today is not stepped again.
"""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_team_schedule as ts
from app.services import warmup_helper_thread as wt
from app.services import peer_pacer, send_gate
from app.models.warmup_helpers import (
    WarmupHelper, WarmupHelperTask, WarmupHelperThread, WarmupTeamEnrollment,
)
from app.models.warmup_mesh import WarmupEnrollment
from app.models.account import AccountStatus

# 11:00 Tehran on a fixed date (inside waking hours 09:00–21:00).
NOW = datetime(2026, 5, 4, 11, 0)


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset(); send_gate.clear_live_cache()
    yield
    peer_pacer.reset(); send_gate.clear_live_cache()


# ── pure schedule math ────────────────────────────────────────────────────────
def test_team_day_index_by_date():
    assert ts.team_day_index(NOW, NOW) == 0
    assert ts.team_day_index(NOW - timedelta(days=3), NOW) == 3
    assert ts.team_day_index(None, NOW) == 0


def test_daily_step_budget_ramp():
    assert ts.daily_step_budget(0) == 1
    assert ts.daily_step_budget(1) == 1
    assert ts.daily_step_budget(2) == 2
    assert ts.daily_step_budget(9) == 2
    assert ts.daily_step_budget(10) == 0     # cycle complete
    assert ts.daily_step_budget(15) == 0


def test_stepped_today_and_selection():
    t_today = WarmupHelperThread(helper_id=uuid.uuid4(), cold_instance_id="C1", step_count=1,
                                 status=wt.STATUS_ACTIVE)
    t_today.last_step_at = NOW - timedelta(hours=1)     # same Tehran date
    t_old = WarmupHelperThread(helper_id=uuid.uuid4(), cold_instance_id="C1", step_count=0,
                               status=wt.STATUS_ACTIVE)
    t_old.last_step_at = NOW - timedelta(days=2)
    assert ts.stepped_today(t_today, NOW) is True
    assert ts.stepped_today(t_old, NOW) is False
    # selection prefers the not-stepped-today, lowest-step_count thread
    chosen = ts.select_thread_for_step([t_today, t_old], NOW)
    assert chosen is t_old
    # once all threads stepped today → none due
    assert ts.select_thread_for_step([t_today], NOW) is None


def test_paused_thread_not_selected():
    paused = WarmupHelperThread(helper_id=uuid.uuid4(), cold_instance_id="C1", step_count=0,
                                status=wt.STATUS_PAUSED)
    assert ts.select_thread_for_step([paused], NOW) is None


# ── engine fake ──────────────────────────────────────────────────────────────
def _acc(iid, warm=False):
    return SimpleNamespace(instance_id=iid, api_token="t", phone=f"9890{iid}", name=iid,
                           is_warm_peer=warm, status=AccountStatus.active,
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


class FakeResult:
    def __init__(self, scalars=None, rows=None):
        self._s = list(scalars) if scalars is not None else []
        self._rows = rows
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()
    def all(self): return list(self._rows) if self._rows is not None else list(self._s)
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class FakeDB:
    def __init__(self, *, enrolls, accounts, mesh_enr, helpers, tasks, threads,
                 sender_cfgs=None, briefs=None):
        self.enrolls = enrolls; self.accounts = accounts; self.mesh_enr = mesh_enr
        self.helpers = helpers; self.tasks = tasks; self.threads = threads
        self.sender_cfgs = sender_cfgs or []; self.briefs = briefs or []
        self.added = []; self.commits = 0
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_team_enrollment" in sql:
            return FakeResult(scalars=[e for e in self.enrolls if e.is_enabled])
        if "warmup_enrollment" in sql:
            # both the mesh enrollment lookup and enr_map use this table
            if "instance_id =" in sql:
                return FakeResult(scalars=[self.mesh_enr] if self.mesh_enr else [])
            return FakeResult(rows=[(self.mesh_enr.instance_id, self.mesh_enr.state, True)]
                              if self.mesh_enr else [])
        if "warmup_sender_config" in sql:
            return FakeResult(scalars=list(self.sender_cfgs))
        if "outreach_brief" in sql:
            return FakeResult(scalars=list(self.briefs))
        if "warmup_helper_thread" in sql:
            return FakeResult(scalars=list(self.threads))
        if "warmup_helper_task" in sql:
            if "helper_id" in sql and "cold_instance_id" in sql and "status" not in sql \
               and "select warmup_helper_task.helper_id" in sql:
                return FakeResult(rows=[(t.helper_id,) for t in self.tasks])
            return FakeResult(scalars=list(self.tasks))
        if "warmup_helper" in sql:
            return FakeResult(scalars=list(self.helpers))
        if "accounts" in sql:
            return FakeResult(scalars=[a for a in self.accounts if a.status == AccountStatus.active])
        return FakeResult()
    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def get(self, model, pk):
        for h in self.helpers:
            if getattr(h, "id", None) == pk: return h
        return None


def _factory(store):
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): store["phone"] = p; store["text"] = t; return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    return factory


def _setup(mesh_authorized_at):
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1", job_title="کارشناس", years_experience=5)
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status="pending")
    task.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=0,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    te = WarmupTeamEnrollment(cold_instance_id="C1", is_enabled=True,
                              enrolled_at=NOW - timedelta(days=3), day_index=0)
    mesh = WarmupEnrollment(instance_id="C1", state="RECEIVING", authorized_at=mesh_authorized_at)
    cold = _acc("C1"); cold.phone = "989048249532"
    sender = _acc("P1", warm=True)
    db = FakeDB(enrolls=[te], accounts=[cold, sender], mesh_enr=mesh,
                helpers=[helper], tasks=[task], threads=[thread])
    return db, helper, thread, te


@pytest.mark.asyncio
async def test_cold_in_cooldown_no_send(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    db, helper, thread, te = _setup(NOW - timedelta(hours=2))   # cold authorized 2h ago → cooling
    store = {}
    res = await ts.run_team_schedule_tick(db, now=NOW, client_factory=_factory(store),
                                          rng=random.Random(1))
    assert res["acted"] == 0
    assert "phone" not in store            # no ask sent during the 24h cooldown
    assert thread.step_count == 0


@pytest.mark.asyncio
async def test_after_cooldown_sends_step_and_advances(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    db, helper, thread, te = _setup(NOW - timedelta(hours=30))  # cooldown cleared
    store = {}
    async def ai(*, name, topic, step_count, brief, profile_line):
        return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک داشتم"
    res = await ts.run_team_schedule_tick(db, now=NOW, client_factory=_factory(store),
                                          ai_fn=ai, rng=random.Random(2))
    assert res["acted"] == 1 and res["sent"] is True
    assert res["day_index"] == 3
    assert store["phone"] == "989111111111"           # ask went to the contact
    assert "https://wa.me/989048249532" in store["text"]
    assert thread.step_count == 1 and thread.last_step_at == NOW


@pytest.mark.asyncio
async def test_no_second_step_same_thread_same_day(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    db, helper, thread, te = _setup(NOW - timedelta(hours=30))
    thread.last_step_at = NOW - timedelta(hours=2)     # already stepped today
    thread.step_count = 1
    store = {}
    res = await ts.run_team_schedule_tick(db, now=NOW, client_factory=_factory(store),
                                          rng=random.Random(3))
    assert res["acted"] == 0                            # no 2nd step for the same thread today
    assert "phone" not in store


@pytest.mark.asyncio
async def test_outside_waking_hours_noop():
    night = datetime(2026, 5, 4, 3, 0)                 # 03:00 Tehran
    db, helper, thread, te = _setup(NOW - timedelta(hours=30))
    res = await ts.run_team_schedule_tick(db, now=night, client_factory=_factory({}))
    assert res["acted"] == 0 and res["in_hours"] is False


# ── enrollment CRUD ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_set_team_enrolled_stamps_clock():
    class _DB:
        def __init__(s): s.added = []; s.commits = 0
        async def execute(s, q): return FakeResult(scalars=[])
        def add(s, o): s.added.append(o)
        async def flush(s): pass
        async def commit(s): s.commits += 1
        async def refresh(s, o): pass
    db = _DB()
    enr = await ts.set_team_enrolled(db, "C1", True, now=NOW)
    assert enr.is_enabled is True and enr.enrolled_at == NOW and enr.day_index == 0
