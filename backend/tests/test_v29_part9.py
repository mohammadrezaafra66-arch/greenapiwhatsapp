"""V29 PART 9 «همکاری تیمی» — the dedicated event log (Shamsi dates).

Proves:
  • record() adds a log row with the right event fields (best-effort, no commit);
  • render_row renders a Shamsi date/time + Persian event label;
  • list_events filters by sender / cold account / event type (SQL-routed fake);
  • the detection path (PART 4) writes both an 'incoming' and a 'thank_you' log row.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_log as tclog
from app.services import warmup_helper_engine as he
from app.services import warmup_helper_service as hs
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperThread, WarmupHelperLog
from app.models.account import AccountStatus
from app.services.warmup_state import WarmupState


# ── record + render ───────────────────────────────────────────────────────────
def test_record_adds_row():
    class _DB:
        def __init__(s): s.added = []
        def add(s, o): s.added.append(o)
    db = _DB()
    row = tclog.record(db, event_type=tclog.EVENT_ASK, from_instance_id="P1",
                       to_phone="989111111111", sender_instance_id="P1", cold_instance_id="C1",
                       message_sent="سلام")
    assert row in db.added
    assert row.event_type == "ask" and row.from_instance_id == "P1"
    assert row.to_phone == "989111111111" and row.message_sent == "سلام"


def test_render_row_has_shamsi_and_fa():
    r = WarmupHelperLog(event_type=tclog.EVENT_COLD_REPLY, from_instance_id="C1",
                        to_phone="989111111111", message_sent="بله فرستادم")
    r.id = uuid.uuid4()
    r.created_at = datetime(2026, 5, 4, 8, 30)      # naive UTC
    out = tclog.render_row(r)
    assert out["event_type"] == "cold_reply"
    assert out["event_fa"] == "پاسخ اکانت سرد"
    assert out["shamsi"] is not None and "/" in out["shamsi"]   # Shamsi date string
    assert out["message_sent"] == "بله فرستادم"


# ── list_events filtering ─────────────────────────────────────────────────────
class _Res:
    def __init__(self, scalars=None): self._s = scalars or []
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()


class _FilterDB:
    """Captures the compiled WHERE so we can assert the filters were applied."""
    def __init__(self, rows): self.rows = rows; self.last_sql = ""
    async def execute(self, q):
        try: self.last_sql = str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: self.last_sql = str(q).lower()
        return _Res(scalars=self.rows)


@pytest.mark.asyncio
async def test_list_events_applies_filters():
    r = WarmupHelperLog(event_type=tclog.EVENT_ASK, sender_instance_id="P1", cold_instance_id="C1")
    r.id = uuid.uuid4(); r.created_at = datetime(2026, 5, 4, 8, 30)
    db = _FilterDB([r])
    out = await tclog.list_events(db, sender_instance_id="P1", cold_instance_id="C1",
                                  event_type="ask")
    assert len(out) == 1
    assert "p1" in db.last_sql and "c1" in db.last_sql and "ask" in db.last_sql


# ── detection path writes incoming + thank_you log rows ──────────────────────
class FakeResult:
    def __init__(self, scalars=None, rows=None):
        self._s = list(scalars) if scalars is not None else []; self._rows = rows
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
        if "warmup_helper_thread" in sql: return FakeResult(scalars=list(self.threads))
        if "group_keyword" in sql: return FakeResult(rows=[])
        if "warmup_helper_task" in sql:
            rows = list(self.tasks)
            if "status" in sql: rows = [t for t in rows if t.status in sql]
            if "cold_instance_id =" in sql: rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return FakeResult(scalars=rows)
        if "warmup_helper" in sql:
            matched = [h for h in self.helpers if h.phone and h.phone in sql]
            return FakeResult(scalars=matched or self.helpers)
        if "warmup_enrollment" in sql: return FakeResult(rows=list(self.enrollments))
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
async def test_incoming_writes_incoming_and_thankyou_log(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    NOW = datetime(2026, 5, 4, 11, 0)
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_ASKED)
    task.id = uuid.uuid4(); task.asked_at = NOW - timedelta(minutes=30)
    db = FakeDB([helper], [task], [], [_acc("P1", warm=True), _acc("C1")],
                [("C1", WarmupState.RECEIVING.value, True)])
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        c.send_message = AsyncMock(return_value="MID"); return c
    await he.handle_helper_incoming(db, "C1", "989111111111", NOW,
                                    message_text="سلام فرستادم", client_factory=factory)
    logs = [o for o in db.added if isinstance(o, WarmupHelperLog)]
    kinds = {l.event_type for l in logs}
    assert tclog.EVENT_INCOMING in kinds and tclog.EVENT_THANK_YOU in kinds
