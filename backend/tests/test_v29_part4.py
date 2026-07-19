"""V29 PART 4 «همکاری تیمی» — thread-aware detection + thank-you + safety flagging.

Proves:
  • detection matches on the contact's PRIMARY *or* «شماره کاری» secondary phone;
  • an incoming success updates the thread (last_step_at) and still fires the thank-you;
  • a forbidden/sensitive word in the incoming text PAUSES only that thread + raises an alert
    AND skips the thank-you, while leaving the rest of the feature running;
  • find_forbidden_word / load-list behavior is correct.
"""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_engine as he
from app.services import warmup_helper_service as hs
from app.services import warmup_thread_safety as safety
from app.services import warmup_helper_thread as wt
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperThread
from app.models.account import AccountStatus
from app.services.warmup_state import WarmupState

TEHRAN_11AM = datetime(2026, 5, 4, 11, 0)


def _acc(iid, warm=False):
    return SimpleNamespace(instance_id=iid, api_token="t", phone=f"9890{iid}", name=iid,
                           is_warm_peer=warm, status=AccountStatus.active,
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


class FakeResult:
    def __init__(self, scalars=None, rows=None, scalar=None):
        self._scalars = list(scalars) if scalars is not None else []
        self._rows = rows
        self._scalar = scalar
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._scalars)
        return _S()
    def all(self): return list(self._rows) if self._rows is not None else list(self._scalars)
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class FakeDB:
    """SQL-string-routed fake that DISTINGUISHES warmup_helper_thread from warmup_helper."""
    def __init__(self, helpers=None, tasks=None, threads=None, accounts=None,
                 enrollments=None, forbidden_words=None):
        self.helpers = helpers or []
        self.tasks = tasks or []
        self.threads = threads or []
        self.accounts = accounts or []
        self.enrollments = enrollments or []
        self.forbidden_words = forbidden_words or []
        self.added = []
        self.commits = 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_helper_thread" in sql:
            digits_match = [t for t in self.threads]
            # match by helper_id + cold in SQL when present
            return FakeResult(scalars=list(self.threads))
        if "group_keyword" in sql:
            return FakeResult(rows=[(w,) for w in self.forbidden_words])
        if "warmup_helper_task" in sql:
            rows = list(self.tasks)
            if "status" in sql:
                rows = [t for t in rows if t.status in sql]
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return FakeResult(scalars=rows)
        if "warmup_helper" in sql:                 # WarmupHelper entity
            # primary OR secondary phone match — return helpers whose phone appears in the SQL
            matched = [h for h in self.helpers
                       if (h.phone and h.phone in sql) or
                          (getattr(h, "phone_secondary", None) and h.phone_secondary in sql)]
            return FakeResult(scalars=matched or self.helpers)
        if "warmup_enrollment" in sql:
            return FakeResult(rows=list(self.enrollments))
        if "accounts" in sql:
            active = [a for a in self.accounts if a.status == AccountStatus.active]
            return FakeResult(scalars=active)
        return FakeResult()

    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def get(self, model, pk):
        for h in self.helpers:
            if getattr(h, "id", None) == pk:
                return h
        return None


def _factory(store):
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _send(phone, text):
            store["phone"] = phone; store["text"] = text; return "MID"
        c.send_message = AsyncMock(side_effect=_send)
        return c
    return factory


# ── pure forbidden-word matcher ──────────────────────────────────────────────
def test_find_forbidden_word():
    assert safety.find_forbidden_word("این یک کلاهبرداری است", ["کلاهبرداری"]) == "کلاهبرداری"
    assert safety.find_forbidden_word("سلام خوبی", ["کلاهبرداری"]) is None
    assert safety.find_forbidden_word("", ["x"]) is None
    # case-insensitive on latin
    assert safety.find_forbidden_word("send CVV now", ["cvv"]) == "cvv"


# ── detection matches secondary phone ────────────────────────────────────────
@pytest.mark.asyncio
async def test_incoming_matches_secondary_phone(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="مریم کریمی", phone="989111111111",
                          phone_secondary="989135550000", is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_ASKED)
    task.id = uuid.uuid4(); task.asked_at = TEHRAN_11AM - timedelta(minutes=20)
    db = FakeDB(helpers=[helper], tasks=[task], threads=[],
                accounts=[_acc("P1", warm=True), _acc("C1")],
                enrollments=[("C1", WarmupState.RECEIVING.value, True)])
    store = {}
    # incoming from the SECONDARY «شماره کاری» number
    res = await he.handle_helper_incoming(db, "C1", "989135550000@c.us", TEHRAN_11AM,
                                          message_text="سلام رسید", client_factory=_factory(store))
    assert res is not None and res["thanked"] is True and res["thread_paused"] is False
    assert task.status == hs.STATUS_DONE
    assert store["phone"] == "989111111111"          # thank-you to the primary
    # a new thread was created + stamped
    assert any(isinstance(o, WarmupHelperThread) for o in db.added)


# ── forbidden word pauses only that thread + skips thank-you ─────────────────
@pytest.mark.asyncio
async def test_forbidden_word_pauses_thread_and_skips_thankyou(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_ASKED)
    task.id = uuid.uuid4(); task.asked_at = TEHRAN_11AM - timedelta(minutes=20)
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=1,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    db = FakeDB(helpers=[helper], tasks=[task], threads=[thread],
                accounts=[_acc("P1", warm=True), _acc("C1")],
                enrollments=[("C1", WarmupState.RECEIVING.value, True)])
    store = {}
    res = await he.handle_helper_incoming(
        db, "C1", "989111111111", TEHRAN_11AM,
        message_text="بیا با هم کلاهبرداری کنیم", client_factory=_factory(store))
    assert res["thread_paused"] is True
    assert res["thanked"] is False               # thank-you skipped for a flagged thread
    assert thread.status == wt.STATUS_PAUSED
    assert "phone" not in store                   # no thank-you send happened
    # an admin alert row was added
    from app.models.warmup_helpers import WarmupThreadAlert
    assert any(isinstance(o, WarmupThreadAlert) for o in db.added)


# ── clean incoming keeps the thread active + thanks ──────────────────────────
@pytest.mark.asyncio
async def test_clean_incoming_thanks_and_keeps_active(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="سارا احمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_REMINDED)
    task.id = uuid.uuid4(); task.asked_at = TEHRAN_11AM - timedelta(hours=2)
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=1,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    db = FakeDB(helpers=[helper], tasks=[task], threads=[thread],
                accounts=[_acc("P1", warm=True), _acc("C1")],
                enrollments=[("C1", WarmupState.RECEIVING.value, True)])
    store = {}
    res = await he.handle_helper_incoming(db, "C1", "989111111111", TEHRAN_11AM,
                                          message_text="سلام، پیام رو فرستادم", client_factory=_factory(store))
    assert res["thanked"] is True and res["thread_paused"] is False
    assert thread.status == wt.STATUS_ACTIVE
    assert thread.last_step_at == TEHRAN_11AM
    assert "ممنون" in store["text"]


# ── scan_and_flag returns None on clean text ─────────────────────────────────
@pytest.mark.asyncio
async def test_scan_and_flag_clean_is_noop():
    thread = WarmupHelperThread(helper_id=uuid.uuid4(), cold_instance_id="C1",
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    db = FakeDB()
    alert = await safety.scan_and_flag(db, thread, "سلام خوبی", safety.DIR_INBOUND,
                                       words=["کلاهبرداری"])
    assert alert is None and thread.status == wt.STATUS_ACTIVE
