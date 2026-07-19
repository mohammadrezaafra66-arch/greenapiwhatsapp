"""V30 PART 9 — final wiring + integrated regression.

Proves the new rules are wired together on the LIVE team-schedule ask path and that the beat
schedule registers every «همکاری تیمی» tick, including the new thank-you tick:
  • the beat schedule registers process-team-schedule (300s), process-cold-replies (120s),
    process-thank-yous (120s), process-helper-warmup;
  • an ask fires ONLY inside 09:00–19:00 Tehran, ONLY when the sender's 20-min spacing has elapsed,
    and the sent text is varied and carries an emoji + the cold account's wa.me link — all in one run.
"""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_team_schedule as ts
from app.services import warmup_helper_thread as wt
from app.services import warmup_ask_spacing as spacing
from app.services import peer_pacer
from app.services.warmup_content import has_emoji
from app.models.warmup_helpers import (
    WarmupHelper, WarmupHelperTask, WarmupHelperThread, WarmupTeamEnrollment,
)
from app.models.warmup_mesh import WarmupEnrollment
from app.models.account import AccountStatus

IN_WINDOW = datetime(2026, 5, 4, 11, 0)     # 11:00 Tehran — inside 09–19
OUT_WINDOW = datetime(2026, 5, 4, 20, 0)    # 20:00 Tehran — inside mesh 09–21 but OUTSIDE 09–19


# ── beat wiring ───────────────────────────────────────────────────────────────
def test_beat_registers_all_team_collab_ticks():
    from app.workers.celery_app import celery_app
    sched = celery_app.conf.beat_schedule
    assert sched["process-team-schedule"]["schedule"] == 300.0
    assert sched["process-cold-replies"]["schedule"] == 120.0
    assert sched["process-thank-yous"]["task"] == "tasks.process_thank_yous"
    assert sched["process-thank-yous"]["schedule"] == 120.0
    assert "process-helper-warmup" in sched


# ── integrated ask path harness (mirrors test_v30_part2) ─────────────────────
def _acc(iid, warm=False):
    return SimpleNamespace(instance_id=iid, api_token="t", phone=f"9890{iid}", name=iid,
                           is_warm_peer=warm, status=AccountStatus.active,
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


class _Res:
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


class _DB:
    def __init__(self, *, enrolls, accounts, mesh_enr, helpers, tasks, threads):
        self.enrolls = enrolls; self.accounts = accounts; self.mesh_enr = mesh_enr
        self.helpers = helpers; self.tasks = tasks; self.threads = threads
        self.added = []; self.commits = 0
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_team_enrollment" in sql:
            return _Res(scalars=[e for e in self.enrolls if e.is_enabled])
        if "warmup_enrollment" in sql:
            if "instance_id =" in sql:
                return _Res(scalars=[self.mesh_enr] if self.mesh_enr else [])
            return _Res(rows=[(self.mesh_enr.instance_id, self.mesh_enr.state, True)] if self.mesh_enr else [])
        if "warmup_sender_config" in sql or "outreach_brief" in sql:
            return _Res(scalars=[])
        if "warmup_helper_thread" in sql:
            return _Res(scalars=list(self.threads))
        if "warmup_helper_log" in sql:
            return _Res(scalars=[])          # no prior asks logged
        if "warmup_helper_task" in sql:
            if "select warmup_helper_task.helper_id" in sql:
                return _Res(rows=[(t.helper_id,) for t in self.tasks])
            return _Res(scalars=list(self.tasks))
        if "warmup_helper" in sql:
            return _Res(scalars=list(self.helpers))
        if "accounts" in sql:
            return _Res(scalars=[a for a in self.accounts if a.status == AccountStatus.active])
        return _Res()
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


def _setup():
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1", job_title="کارشناس", years_experience=5)
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status="pending")
    task.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=0,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    te = WarmupTeamEnrollment(cold_instance_id="C1", is_enabled=True,
                              enrolled_at=IN_WINDOW - timedelta(days=3), day_index=0)
    mesh = WarmupEnrollment(instance_id="C1", state="RECEIVING",
                            authorized_at=IN_WINDOW - timedelta(hours=30))
    cold = _acc("C1"); cold.phone = "989048249532"
    sender = _acc("P1", warm=True)
    return _DB(enrolls=[te], accounts=[cold, sender], mesh_enr=mesh, helpers=[helper],
               tasks=[task], threads=[thread]), thread


async def _ai(*, name, topic, step_count, brief, profile_line):
    return f"سلام {name} جان، درباره‌ی {topic} یه لطف کوچیک ازت داشتم"   # no emoji → backstop adds one


@pytest.mark.asyncio
async def test_no_ask_outside_team_window(monkeypatch):
    monkeypatch.setattr(spacing, "last_ask_at_for_sender", AsyncMock(return_value=None))
    db, thread = _setup()
    res = await ts.run_team_schedule_tick(db, now=OUT_WINDOW, client_factory=_factory({}), ai_fn=_ai)
    assert res["acted"] == 0 and res.get("in_team_hours") is False


@pytest.mark.asyncio
async def test_no_ask_when_spacing_not_elapsed(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(spacing, "last_ask_at_for_sender",
                        AsyncMock(return_value=IN_WINDOW - timedelta(minutes=5)))
    db, thread = _setup()
    store = {}
    res = await ts.run_team_schedule_tick(db, now=IN_WINDOW, client_factory=_factory(store), ai_fn=_ai)
    assert res["acted"] == 0 and "phone" not in store


@pytest.mark.asyncio
async def test_all_rules_together_ask_fires_varied_emoji_in_window(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(spacing, "last_ask_at_for_sender",
                        AsyncMock(return_value=IN_WINDOW - timedelta(minutes=25)))   # spacing OK
    db, thread = _setup()
    store = {}
    res = await ts.run_team_schedule_tick(db, now=IN_WINDOW, client_factory=_factory(store),
                                          ai_fn=_ai, rng=random.Random(1))
    assert res["acted"] == 1 and res["sent"] is True         # inside window + spacing elapsed
    assert store["phone"] == "989111111111"
    assert has_emoji(store["text"])                          # PART 5 emoji backstop
    assert "https://wa.me/989048249532" in store["text"]      # cold account referenced via link only
    assert "رضا محمدی" in store["text"]                       # real full name
    assert thread.step_count == 1
