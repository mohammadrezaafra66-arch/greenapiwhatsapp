"""V33 PART 5 — final wiring + end-to-end simulation across PART 1–4.

Scenario 1 (no-response lifecycle, driven through the REAL run_helper_tick):
  a previously-"stuck" pending task is asked (PART 1 — bounded queue progresses), then with no
  completion gets EXACTLY 2 reminders and finally goes terminal `no_response` with its thread closed
  — never a 3rd reminder (PART 4).

Scenario 2 (completion + ceiling-bounded escalation, through the REAL handle_helper_incoming):
  a contact already at the 2-cold ceiling completes one task → it is marked done, thanked, and the
  completion escalation assigns NO new cold account (PART 2 ceiling respected, PART 4 thank-you).
"""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_engine as he
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_thread as wt
from app.services import peer_pacer
from app.models.warmup_helpers import (
    WarmupHelper, WarmupHelperTask, WarmupHelperThread, WarmupHelperConfig, WarmupTeamEnrollment,
)
from app.models.account import Account, AccountStatus
from app.services.warmup_state import WarmupState

BASE = datetime(2026, 5, 4, 11, 0)
WINDOW = hs.REMINDER_AFTER_MINUTES


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset()
    yield
    peer_pacer.reset()


class _R:
    def __init__(self, scalars=None, rows=None):
        self._s = list(scalars) if scalars is not None else []
        self._rows = list(rows) if rows is not None else []

    def scalars(self):
        data = self._s

        class _S:
            def all(_s):
                return list(data)
        return _S()

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._s[0] if self._s else None

    def scalar(self):
        return self._s[0] if self._s else 0


class _StatefulDB:
    """One shared, stateful fake routing every query run_helper_tick / handle_helper_incoming issue,
    faithfully modelling expire's numeric WHERE via `self.now`."""
    def __init__(self, *, helpers, tasks, threads, accounts, enrollments, config=None,
                 team_enrolls=None):
        self.helpers, self.tasks, self.threads = list(helpers), list(tasks), list(threads)
        self.accounts, self.enrollments = list(accounts), list(enrollments)
        self.config = config
        self.team_enrolls = list(team_enrolls or [])
        self.now = BASE
        self.added, self.commits = [], 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_helper_config" in sql:
            return _R(scalars=[self.config] if self.config else [])
        if "warmup_team_enrollment" in sql:
            if "cold_instance_id =" in sql:
                m = [e for e in self.team_enrolls if e.cold_instance_id.lower() in sql]
                return _R(scalars=m)
            return _R(scalars=[e for e in self.team_enrolls if e.is_enabled])
        if "warmup_helper_thread" in sql:
            rows = self.threads
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return _R(scalars=list(rows))
        if "outreach_brief" in sql or "warmup_helper_log" in sql or "group_keyword" in sql:
            return _R(scalars=[], rows=[])
        if "warmup_helper_task" in sql:
            if "warmup_helper_task.id" in sql:                          # entity select
                rows = list(self.tasks)
                if "reminder_count >=" in sql:                          # expire WHERE (numeric)
                    cutoff = self.now - timedelta(minutes=WINDOW)
                    rows = [t for t in rows
                            if t.status == hs.STATUS_REMINDED
                            and int(getattr(t, "reminder_count", 0) or 0) >= hs.MAX_REMINDERS
                            and t.reminded_at is not None and t.reminded_at <= cutoff]
                else:
                    if "status in" in sql or "status =" in sql:
                        rows = [t for t in rows if f"'{t.status}'" in sql]
                    if "cold_instance_id =" in sql:
                        rows = [t for t in rows if t.cold_instance_id.lower() in sql]
                    if "helper_id =" in sql:
                        rows = [t for t in rows if str(t.helper_id).replace("-","").lower() in sql]
                return _R(scalars=rows)
            # distinguish the SELECTED columns (before FROM) from WHERE references
            select_part = sql.split("from")[0]
            sel_h = "warmup_helper_task.helper_id" in select_part
            sel_c = "warmup_helper_task.cold_instance_id" in select_part
            if sel_h and sel_c:                                         # ensure pairs
                return _R(rows=[(t.helper_id, t.cold_instance_id) for t in self.tasks])
            if sel_c:                                                   # list_cold_accounts_for_helper
                tt = self.tasks
                if "helper_id =" in sql:
                    tt = [t for t in tt if str(t.helper_id).replace("-", "").lower() in sql]
                return _R(rows=[(t.cold_instance_id,) for t in tt])
            tt = self.tasks                                             # helper_id-only (team pairs)
            if "cold_instance_id =" in sql:
                tt = [t for t in tt if t.cold_instance_id.lower() in sql]
            return _R(rows=[(t.helper_id,) for t in tt])
        if "warmup_helper" in sql:                                      # WarmupHelper entity/list
            rows = self.helpers
            phones = [h for h in self.helpers if (h.phone and h.phone in sql)
                      or (getattr(h, "phone_secondary", None) and h.phone_secondary in sql)]
            if phones and "phone" in sql:
                rows = phones
            return _R(scalars=list(rows))
        if "warmup_enrollment" in sql:
            if "instance_id =" in sql:
                return _R(scalars=[])
            return _R(rows=list(self.enrollments))
        if "accounts" in sql:
            match = [a for a in self.accounts if a.instance_id.lower() in sql]
            if match and "instance_id =" in sql:
                return _R(scalars=match)
            return _R(scalars=[a for a in self.accounts if a.status == AccountStatus.active])
        return _R()

    def add(self, o):
        self.added.append(o)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, o):
        pass

    async def delete(self, o):
        for coll in (self.tasks, self.threads, self.helpers):
            if o in coll:
                coll.remove(o)

    async def get(self, model, pk):
        for h in self.helpers:
            if getattr(h, "id", None) == pk:
                return h
        return None


def _acc(iid, *, warm=False, phone=None):
    a = Account(name=f"acc-{iid}", instance_id=iid, api_token="t")
    a.id = uuid.uuid4()
    a.status = AccountStatus.active
    a.is_warm_peer = warm
    a.phone = phone
    return a


def _factory(store):
    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)

        async def _s(p, t):
            store.setdefault("all", []).append({"from": iid, "to": p, "text": t})
            return "MID"
        c.send_message = AsyncMock(side_effect=_s)
        return c
    return factory


# ── Scenario 1: ask → reminder ×2 → no_response, never a 3rd ─────────────────
@pytest.mark.asyncio
async def test_no_response_lifecycle_end_to_end(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("P1", warm=True)
    cold = _acc("C1", phone="989048249532")
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_PENDING)
    task.id = uuid.uuid4()
    task.created_at = BASE - timedelta(minutes=5)
    task.reminder_count = 0
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=0,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)
    db = _StatefulDB(helpers=[helper], tasks=[task], threads=[thread], accounts=[sender, cold],
                     enrollments=[("C1", WarmupState.RECEIVING.value, True)], config=config)
    store = {}
    factory = _factory(store)

    async def tick(at):
        db.now = at
        return await he.run_helper_tick(db, now=at, client_factory=factory, rng=random.Random(1))

    # ask the previously-stuck pending task (PART 1)
    r1 = await tick(BASE)
    assert r1["acted"] == 1 and r1["kind"] == "ask"
    assert task.status == hs.STATUS_ASKED and task.reminder_count == 0

    # reminder #1
    r2 = await tick(BASE + timedelta(minutes=WINDOW + 1))
    assert r2["kind"] == "remind"
    assert task.status == hs.STATUS_REMINDED and task.reminder_count == 1

    # reminder #2 (final)
    r3 = await tick(BASE + timedelta(minutes=2 * WINDOW + 2))
    assert r3["kind"] == "remind"
    assert task.status == hs.STATUS_REMINDED and task.reminder_count == 2

    # window elapses again → terminal no_response, thread closed, NO 3rd reminder
    r4 = await tick(BASE + timedelta(minutes=3 * WINDOW + 3))
    assert r4["acted"] == 0
    assert task.status == hs.STATUS_NO_RESPONSE and task.reminder_count == 2
    assert thread.status == wt.STATUS_DONE

    # exactly 2 reminder messages were sent (1 ask + 2 reminders = 3 sends total)
    assert len(store["all"]) == 3


# ── Scenario 2: completion at ceiling → done + thank-you + NO escalation ─────
@pytest.mark.asyncio
async def test_completion_thanks_and_escalation_respects_ceiling(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = SimpleNamespace(instance_id="P1", api_token="t", phone="989000", name="P1",
                             is_warm_peer=True, status=AccountStatus.active,
                             cooldown_until=None, throttle_until=None, throttle_factor=1.0)
    coldC1 = SimpleNamespace(instance_id="C1", api_token="t", phone="989048249532", name="C1",
                             is_warm_peer=False, status=AccountStatus.active,
                             cooldown_until=None, throttle_until=None, throttle_factor=1.0)
    helper = WarmupHelper(name="مریم کریمی", phone="989111111111", is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    # already at the 2-cold ceiling: C1 (reminded) + C2 (asked)
    t1 = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_REMINDED)
    t1.id = uuid.uuid4(); t1.reminded_at = BASE - timedelta(minutes=50); t1.reminder_count = 1
    t2 = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C2", status=hs.STATUS_ASKED)
    t2.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=1,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    # C1 is team-enrolled → completion escalation is attempted (and must respect the ceiling)
    te = WarmupTeamEnrollment(cold_instance_id="C1", is_enabled=True, enrolled_at=BASE - timedelta(days=2))
    db = _StatefulDB(helpers=[helper], tasks=[t1, t2], threads=[thread], accounts=[sender, coldC1],
                     enrollments=[("C1", WarmupState.RECEIVING.value, True)], team_enrolls=[te])
    store = {}

    res = await he.handle_helper_incoming(db, "C1", "989111111111", BASE,
                                          message_text="سلام، فرستادم", client_factory=_factory(store))
    assert res is not None and res["thanked"] is True
    assert t1.status == hs.STATUS_DONE                      # PART 4 — completion honored
    assert "ممنون" in store["all"][-1]["text"]             # thank-you fired
    # PART 2 — the contact was already at 2 distinct colds, so escalation assigned NO new cold task
    new_tasks = [o for o in db.added if isinstance(o, WarmupHelperTask)]
    assert new_tasks == []
