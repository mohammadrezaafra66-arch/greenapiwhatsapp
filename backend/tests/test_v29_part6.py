"""V29 PART 6 «همکاری تیمی» — confirm the single reminder (45–60 min) works with the
thread-aware flow.

Proves (per ask-STEP, not per legacy global task):
  • no completion within the window → exactly ONE reminder is selected;
  • a reminder never fires a second time (a reminded task is never re-selected);
  • completing AFTER the reminder still marks the task done, fires the thank-you, AND schedules
    the cold-account reply (PART 5) — i.e. the reminder path doesn't break the downstream flow;
  • the 45–60 min window is honored (fires at the 60-min mark, not before 45).
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_engine as he
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_thread as wt
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperThread
from app.models.account import AccountStatus
from app.services.warmup_state import WarmupState

NOW = datetime(2026, 5, 4, 11, 0)


# ── pure reminder_due window ─────────────────────────────────────────────────
def test_reminder_due_window():
    assert hs.reminder_due(NOW - timedelta(minutes=44), NOW) is False   # before window
    assert hs.reminder_due(NOW - timedelta(minutes=60), NOW) is True    # at the 60-min mark
    assert hs.reminder_due(NOW - timedelta(minutes=90), NOW) is True
    assert hs.reminder_due(None, NOW) is False
    assert 45 <= hs.REMINDER_AFTER_MINUTES <= 60


def _task(status, asked_min_ago=None):
    t = WarmupHelperTask(helper_id=uuid.uuid4(), cold_instance_id="C1", status=status)
    t.id = uuid.uuid4(); t.created_at = NOW
    t.asked_at = (NOW - timedelta(minutes=asked_min_ago)) if asked_min_ago is not None else None
    return t


# ── exactly one reminder per step; never a second ────────────────────────────
def test_one_reminder_per_step():
    old_ask = _task(hs.STATUS_ASKED, asked_min_ago=90)
    kind, task = he.select_action([], [old_ask], NOW)
    assert kind == "remind" and task is old_ask


def test_second_reminder_allowed_then_capped():
    # V33 PART 4 — reminders are now capped at exactly 2 (was 1). A once-reminded task gets a 2nd
    # reminder when its window elapses; a twice-reminded task is never selected again.
    once = _task(hs.STATUS_REMINDED, asked_min_ago=200)
    once.reminded_at = NOW - timedelta(minutes=90)
    once.reminder_count = 1
    kind, task = he.select_action([], [once], NOW)
    assert kind == "remind" and task is once
    twice = _task(hs.STATUS_REMINDED, asked_min_ago=200)
    twice.reminded_at = NOW - timedelta(minutes=90)
    twice.reminder_count = 2
    assert he.select_action([], [twice], NOW) is None


def test_no_reminder_before_window():
    fresh = _task(hs.STATUS_ASKED, asked_min_ago=30)   # < 60 → not due
    assert he.select_action([], [fresh], NOW) is None


# ── completing AFTER the reminder still thanks + schedules the cold reply ─────
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
    def __init__(self, helpers, tasks, threads, accounts, enrollments):
        self.helpers = helpers; self.tasks = tasks; self.threads = threads
        self.accounts = accounts; self.enrollments = enrollments
        self.added = []; self.commits = 0
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_helper_thread" in sql:
            return FakeResult(scalars=list(self.threads))
        if "group_keyword" in sql:
            return FakeResult(rows=[])
        if "warmup_helper_task" in sql:
            rows = list(self.tasks)
            if "status" in sql:
                rows = [t for t in rows if t.status in sql]
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return FakeResult(scalars=rows)
        if "warmup_helper" in sql:
            matched = [h for h in self.helpers if h.phone and h.phone in sql]
            return FakeResult(scalars=matched or self.helpers)
        if "warmup_enrollment" in sql:
            return FakeResult(rows=list(self.enrollments))
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


def _acc(iid, warm=False):
    return SimpleNamespace(instance_id=iid, api_token="t", phone=f"9890{iid}", name=iid,
                           is_warm_peer=warm, status=AccountStatus.active,
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


@pytest.mark.asyncio
async def test_complete_after_reminder_thanks_and_schedules_cold_reply(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1")
    helper.id = uuid.uuid4()
    # a task already REMINDED (the reminder fired earlier)
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_REMINDED)
    task.id = uuid.uuid4(); task.asked_at = NOW - timedelta(hours=2)
    task.reminded_at = NOW - timedelta(minutes=50)
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=1,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    db = FakeDB([helper], [task], [thread], [_acc("P1", warm=True), _acc("C1")],
                [("C1", WarmupState.RECEIVING.value, True)])
    store = {}
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): store["phone"] = p; store["text"] = t; return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    res = await he.handle_helper_incoming(db, "C1", "989111111111", NOW,
                                          message_text="سلام، فرستادم", client_factory=factory)
    # thank-you still fires after a reminder
    assert res["thanked"] is True and task.status == hs.STATUS_DONE
    assert "ممنون" in store["text"]
    # and the cold-account reply is scheduled (PART 5)
    assert thread.awaiting_reply is True and thread.pending_reply_at is not None
