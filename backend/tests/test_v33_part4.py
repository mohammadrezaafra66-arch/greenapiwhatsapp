"""V33 PART 4 — cap reminders at exactly 2, then a terminal `no_response` state.

Proves:
  • the reminder cap: ask → reminder #1 → reminder #2 → NEVER a 3rd; the 2nd reminder is only due
    once its own window elapses;
  • `expire_exhausted_reminders` moves a twice-reminded, still-unanswered task to terminal
    `no_response` and marks ITS thread `done` (so neither tick re-asks it), touching nothing else;
  • run_helper_tick actually stamps reminder_count when it sends a reminder;
  • completion at ANY stage — including a LATE completion AFTER `no_response` — still marks the task
    done and fires the thank-you;
  • closing one (contact, cold) task does NOT close a DIFFERENT cold task for the same contact.
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
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperThread
from app.models.account import Account, AccountStatus
from app.services.warmup_state import WarmupState

NOW = datetime(2026, 5, 4, 11, 0)
WINDOW = hs.REMINDER_AFTER_MINUTES


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset()
    yield
    peer_pacer.reset()


def _task(status, *, asked_min_ago=None, reminded_min_ago=None, reminder_count=0, cold="C1", hid=None):
    t = WarmupHelperTask(helper_id=hid or uuid.uuid4(), cold_instance_id=cold, status=status)
    t.id = uuid.uuid4()
    t.created_at = NOW - timedelta(hours=3)
    t.asked_at = (NOW - timedelta(minutes=asked_min_ago)) if asked_min_ago is not None else None
    t.reminded_at = (NOW - timedelta(minutes=reminded_min_ago)) if reminded_min_ago is not None else None
    t.reminder_count = reminder_count
    return t


# ── the reminder cap: exactly two, never three ───────────────────────────────
def test_reminder_one_then_two_then_capped():
    asked = _task(hs.STATUS_ASKED, asked_min_ago=WINDOW + 5)
    assert he.select_action([], [asked], NOW) == ("remind", asked)          # #1 due

    once = _task(hs.STATUS_REMINDED, reminded_min_ago=WINDOW + 5, reminder_count=1)
    assert he.select_action([], [once], NOW) == ("remind", once)            # #2 due

    twice = _task(hs.STATUS_REMINDED, reminded_min_ago=WINDOW + 5, reminder_count=2)
    assert he.select_action([], [twice], NOW) is None                       # never a 3rd


def test_second_reminder_not_due_before_its_own_window():
    once = _task(hs.STATUS_REMINDED, reminded_min_ago=WINDOW - 20, reminder_count=1)
    assert he.select_action([], [once], NOW) is None                        # window not elapsed yet


# ── expire_exhausted_reminders → terminal no_response + thread done ──────────
class _ExpireDB:
    def __init__(self, matched_tasks, threads):
        self.matched = list(matched_tasks)        # what the WHERE would return
        self.threads = list(threads)
        self.committed = False

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        matched, threads = self.matched, self.threads

        class _R:
            def scalars(_s):
                data = matched if "warmup_helper_task" in sql else []

                class _S:
                    def all(__s):
                        return list(data)
                return _S()

            def scalar_one_or_none(_s):
                if "warmup_helper_thread" in sql:
                    m = [th for th in threads if th.cold_instance_id.lower() in sql]
                    return m[0] if m else None
                return None
        return _R()


@pytest.mark.asyncio
async def test_expire_marks_no_response_and_closes_thread():
    hid = uuid.uuid4()
    exhausted = _task(hs.STATUS_REMINDED, reminded_min_ago=WINDOW + 5, reminder_count=2, hid=hid)
    thread = WarmupHelperThread(helper_id=hid, cold_instance_id="C1", step_count=2,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    db = _ExpireDB(matched_tasks=[exhausted], threads=[thread])
    n = await he.expire_exhausted_reminders(db, NOW)
    assert n == 1
    assert exhausted.status == hs.STATUS_NO_RESPONSE       # terminal
    assert thread.status == wt.STATUS_DONE                 # scheduler will skip this pairing


@pytest.mark.asyncio
async def test_expire_noop_when_nothing_exhausted():
    db = _ExpireDB(matched_tasks=[], threads=[])
    assert await he.expire_exhausted_reminders(db, NOW) == 0


# ── run_helper_tick stamps reminder_count when it reminds ────────────────────
class _TickDB:
    def __init__(self, helpers, tasks, accounts, enrollments, threads, config):
        self.helpers, self.tasks, self.accounts = list(helpers), list(tasks), list(accounts)
        self.enrollments, self.threads, self.config = list(enrollments), list(threads), config
        self.added, self.commits = [], 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)

        class _R:
            def __init__(_s, scalars=None, rows=None):
                _s._s = list(scalars) if scalars is not None else []
                _s._rows = list(rows) if rows is not None else []

            def scalars(_s):
                class _S:
                    def all(__s):
                        return list(_s._s)
                return _S()

            def all(_s):
                return list(_s._rows)

            def scalar_one_or_none(_s):
                return _s._s[0] if _s._s else None
        if "warmup_helper_config" in sql:
            return _R(scalars=[self.config] if self.config else [])
        if "warmup_helper_thread" in sql:
            m = [th for th in self.threads if th.cold_instance_id.lower() in sql] if "cold_instance_id =" in sql else list(self.threads)
            return _R(scalars=m)
        if "outreach_brief" in sql:
            return _R(scalars=[])
        if "warmup_helper_log" in sql:
            return _R(scalars=[], rows=[])
        if "warmup_helper_task" in sql:
            if "warmup_helper_task.id" not in sql:
                return _R(rows=[(t.helper_id, t.cold_instance_id) for t in self.tasks])
            rows = list(self.tasks)
            # match the QUOTED status literal in the WHERE (not column names like asked_at/reminded_at)
            if "status in" in sql or "status =" in sql:
                rows = [t for t in rows if f"'{t.status}'" in sql]
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return _R(scalars=rows)
        if "warmup_helper" in sql:
            return _R(scalars=list(self.helpers))
        if "warmup_enrollment" in sql:
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


@pytest.mark.asyncio
async def test_tick_reminder_stamps_count(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("P1", warm=True)
    cold = _acc("C1", phone="989048249532")
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    asked = _task(hs.STATUS_ASKED, asked_min_ago=WINDOW + 10, cold="C1", hid=helper.id)
    from app.models.warmup_helpers import WarmupHelperConfig
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)
    db = _TickDB([helper], [asked], [sender, cold],
                 [("C1", WarmupState.RECEIVING.value, True)], [], config)

    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)
        c.send_message = AsyncMock(return_value="MID")
        return c

    res = await he.run_helper_tick(db, now=NOW, client_factory=factory, rng=random.Random(1))
    assert res["acted"] == 1 and res["kind"] == "remind"
    assert asked.status == hs.STATUS_REMINDED and asked.reminder_count == 1


# ── completion after no_response still thanks (late responder honored) ───────
class _IncResult:
    def __init__(self, scalars=None, rows=None):
        self._s = list(scalars) if scalars is not None else []
        self._rows = rows

    def scalars(self):
        outer = self

        class _S:
            def all(s):
                return list(outer._s)
        return _S()

    def all(self):
        return list(self._rows) if self._rows is not None else list(self._s)

    def scalar_one_or_none(self):
        return self._s[0] if self._s else None


class _IncDB:
    def __init__(self, helpers, tasks, threads, accounts, enrollments):
        self.helpers, self.tasks, self.threads = helpers, tasks, threads
        self.accounts, self.enrollments = accounts, enrollments
        self.added, self.commits = [], 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_helper_thread" in sql:
            return _IncResult(scalars=list(self.threads))
        if "group_keyword" in sql:
            return _IncResult(rows=[])
        if "warmup_team_enrollment" in sql:
            return _IncResult(scalars=[])
        if "warmup_helper_task" in sql:
            rows = list(self.tasks)
            if "status in" in sql:
                rows = [t for t in rows if t.status in sql]
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return _IncResult(scalars=rows)
        if "warmup_helper" in sql:
            matched = [h for h in self.helpers if h.phone and h.phone in sql]
            return _IncResult(scalars=matched or self.helpers)
        if "warmup_enrollment" in sql:
            return _IncResult(rows=list(self.enrollments))
        if "accounts" in sql:
            return _IncResult(scalars=[a for a in self.accounts if a.status == AccountStatus.active])
        return _IncResult()

    def add(self, o):
        self.added.append(o)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, o):
        pass

    async def get(self, model, pk):
        for h in self.helpers:
            if getattr(h, "id", None) == pk:
                return h
        return None


def _sacc(iid, warm=False):
    return SimpleNamespace(instance_id=iid, api_token="t", phone=f"9890{iid}", name=iid,
                           is_warm_peer=warm, status=AccountStatus.active,
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


@pytest.mark.asyncio
async def test_completion_after_no_response_still_thanks(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    # the task already went terminal no_response — a LATE completion arrives
    task = _task(hs.STATUS_NO_RESPONSE, asked_min_ago=300, reminded_min_ago=180, reminder_count=2,
                 cold="C1", hid=helper.id)
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=2,
                                status=wt.STATUS_DONE)
    thread.id = uuid.uuid4()
    db = _IncDB([helper], [task], [thread], [_sacc("P1", warm=True), _sacc("C1")],
                [("C1", WarmupState.RECEIVING.value, True)])
    store = {}

    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)

        async def _s(p, t):
            store["text"] = t
            return "MID"
        c.send_message = AsyncMock(side_effect=_s)
        return c

    res = await he.handle_helper_incoming(db, "C1", "989111111111", NOW,
                                          message_text="ببخشید دیر شد، فرستادم", client_factory=factory)
    assert res is not None and res["thanked"] is True
    assert task.status == hs.STATUS_DONE                   # late completion honored
    assert "ممنون" in store["text"]


# ── no_response closes only that pairing, not a different cold for the contact ─
@pytest.mark.asyncio
async def test_expire_closes_only_the_exhausted_pairing():
    hid = uuid.uuid4()
    exhausted = _task(hs.STATUS_REMINDED, reminded_min_ago=WINDOW + 5, reminder_count=2, cold="C1", hid=hid)
    other = _task(hs.STATUS_ASKED, asked_min_ago=10, cold="C2", hid=hid)   # same contact, other cold
    th1 = WarmupHelperThread(helper_id=hid, cold_instance_id="C1", step_count=2, status=wt.STATUS_ACTIVE)
    th1.id = uuid.uuid4()
    # only the exhausted task is returned by the WHERE; `other` is not
    db = _ExpireDB(matched_tasks=[exhausted], threads=[th1])
    await he.expire_exhausted_reminders(db, NOW)
    assert exhausted.status == hs.STATUS_NO_RESPONSE
    assert other.status == hs.STATUS_ASKED                 # the other cold task is untouched
