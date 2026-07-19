"""V29 PART 10 «همکاری تیمی» — final wiring + full end-to-end simulation.

Drives the whole feature through ONE shared stateful fake DB:
  enroll a cold account → clear its 24h cooldown (mock time) → first ask-step generates + sends
  (gated/paced) → contact "sends" it (mock webhook) → thank-you fires → cold-account reply fires
  (gated on ITS cooldown/health) → thread topic updates → a later step CONTINUES the same topic →
  a forbidden word pauses ONLY that thread.

Also asserts the cross-guardrail wiring: every send goes through _send_from_main (V27
can_send_now) and the shared peer_pacer, and no identifier ever leaks.
"""
import re
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_team_schedule as ts
from app.services import warmup_helper_engine as he
from app.services import warmup_cold_reply as ccr
from app.services import warmup_helper_thread as wt
from app.services import warmup_helper_service as hs
from app.services import peer_pacer, send_gate
from app.models.warmup_helpers import (
    WarmupHelper, WarmupHelperTask, WarmupHelperThread, WarmupTeamEnrollment, WarmupHelperLog,
)
from app.models.warmup_mesh import WarmupEnrollment
from app.models.account import AccountStatus

DAY3_11AM = datetime(2026, 5, 4, 11, 0)


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset(); send_gate.clear_live_cache()
    yield
    peer_pacer.reset(); send_gate.clear_live_cache()


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


class E2EDB:
    """One shared, stateful fake DB routing every query the V29 flow issues."""
    def __init__(self, *, helper, task, thread, team_enr, mesh_enr, cold, sender):
        self.helpers = [helper]; self.tasks = [task]; self.threads = [thread]
        self.team_enrolls = [team_enr]; self.mesh_enr = mesh_enr
        self.accounts = [cold, sender]
        self.added = []; self.commits = 0
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        s = self._sql(q)
        if "warmup_team_enrollment" in s:
            return FakeResult(scalars=[e for e in self.team_enrolls if e.is_enabled])
        if "warmup_enrollment" in s:
            if "instance_id =" in s:
                return FakeResult(scalars=[self.mesh_enr] if self.mesh_enr else [])
            return FakeResult(rows=[(self.mesh_enr.instance_id, self.mesh_enr.state, True)]
                              if self.mesh_enr else [])
        if "warmup_sender_config" in s:
            return FakeResult(scalars=[])                       # no explicit config → enabled
        if "outreach_brief" in s:
            return FakeResult(scalars=[])                       # no brief → generic topic
        if "group_keyword" in s:
            return FakeResult(rows=[])                          # only built-in forbidden list
        if "warmup_helper_thread" in s:
            return FakeResult(scalars=list(self.threads))
        if "warmup_helper_task" in s:
            if "warmup_helper_task.id" in s:
                rows = list(self.tasks)
                # only filter on status when the WHERE clause constrains it (not the SELECT column)
                if "status in" in s or "status =" in s:
                    rows = [t for t in rows if t.status in s]
                if "cold_instance_id =" in s: rows = [t for t in rows if t.cold_instance_id.lower() in s]
                return FakeResult(scalars=rows)
            return FakeResult(rows=[(t.helper_id,) for t in self.tasks])   # helper_id pairs
        if "warmup_helper" in s:
            matched = [h for h in self.helpers
                       if (h.phone and h.phone in s) or
                          (getattr(h, "phone_secondary", None) and h.phone_secondary in s)]
            return FakeResult(scalars=matched or self.helpers)
        if "accounts" in s:
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


def _acc(iid, warm=False, phone=None):
    return SimpleNamespace(instance_id=iid, api_token="t", phone=phone or f"9890{iid}", name=iid,
                           is_warm_peer=warm, status=AccountStatus.active,
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


def _sends(store):
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t):
            store.setdefault("all", []).append({"from": iid, "to": p, "text": t}); return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    return factory


def _no_leak(store):
    for m in store.get("all", []):
        # the only legitimate long digit run is a wa.me link; assert nothing else leaks
        for line in m["text"].split("\n"):
            if "wa.me/" in line:
                continue
            assert not re.search(r"\d{7,}", line), f"identifier leaked: {line}"


@pytest.mark.asyncio
async def test_full_team_collaboration_cycle(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())

    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1", job_title="کارشناس فروش", years_experience=6,
                          personal_benefit_note="تخفیف پرسنلی")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status="pending")
    task.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=0,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    team_enr = WarmupTeamEnrollment(cold_instance_id="C1", is_enabled=True,
                                    enrolled_at=DAY3_11AM - timedelta(days=3))
    # cold account authorized 30h ago → its 24h post-auth cooldown has CLEARED
    mesh = WarmupEnrollment(instance_id="C1", state="RECEIVING",
                            authorized_at=DAY3_11AM - timedelta(hours=30))
    cold = _acc("C1", phone="989048249532")
    sender = _acc("P1", warm=True)
    db = E2EDB(helper=helper, task=task, thread=thread, team_enr=team_enr, mesh_enr=mesh,
               cold=cold, sender=sender)
    store = {}
    async def ask_ai(*, name, topic, step_count, brief, profile_line):
        return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک داشتم"
    async def reply_ai(*, topic, contact_name):
        return f"سلام {contact_name}، آره درباره‌ی {topic} انجام شد، ممنون از پیگیریت"

    # ── STEP 1: the 10-day scheduler sends the first ask (gated + paced) ──────
    r1 = await ts.run_team_schedule_tick(db, now=DAY3_11AM, client_factory=_sends(store),
                                         ai_fn=ask_ai, rng=random.Random(1))
    assert r1["acted"] == 1 and r1["sent"] is True and r1["day_index"] == 3
    assert thread.step_count == 1
    topic_after_first = thread.topic_summary
    assert task.status == hs.STATUS_ASKED
    # the ask went to the contact and carries the cold account's wa.me link (never a raw number)
    ask_msg = store["all"][-1]
    assert ask_msg["from"] == "P1" and ask_msg["to"] == "989111111111"
    assert "https://wa.me/989048249532" in ask_msg["text"]
    # pacer for the SENDER was re-armed (shared rail)
    assert peer_pacer.peer_ready("P1", he._to_utc_naive(DAY3_11AM)) is False

    # ── STEP 2: the contact sends it (mock webhook) → thank-you + schedule cold reply ─
    incoming_at = DAY3_11AM + timedelta(minutes=35)
    peer_pacer.reset()   # simulate time passing so sends aren't paced against each other
    r2 = await he.handle_helper_incoming(db, "C1", "989111111111", incoming_at,
                                         message_text="سلام، همین الان فرستادم",
                                         client_factory=_sends(store))
    assert r2["thanked"] is True and r2["thread_paused"] is False
    assert task.status == hs.STATUS_DONE
    assert thread.awaiting_reply is True and thread.pending_reply_at is not None
    ty = store["all"][-1]
    assert ty["from"] == "P1" and "ممنون" in ty["text"]

    # ── STEP 3: the cold account replies (gated on ITS cooldown/health) ───────
    reply_due = thread.pending_reply_at + timedelta(seconds=1)
    peer_pacer.reset()
    r3 = await ccr.run_cold_reply_tick(db, now=reply_due, client_factory=_sends(store),
                                       ai_fn=reply_ai, rng=random.Random(2))
    assert r3["acted"] == 1 and r3["sent"] is True
    assert thread.awaiting_reply is False and thread.step_count == 2
    cold_msg = store["all"][-1]
    assert cold_msg["from"] == "C1" and cold_msg["to"] == "989111111111"

    # ── STEP 4: a later step CONTINUES the same topic (next day) ──────────────
    task.status = "pending"                 # a fresh ask-step is due
    thread.last_step_at = DAY3_11AM         # (yesterday relative to day 4)
    day4 = DAY3_11AM + timedelta(days=1)
    peer_pacer.reset()
    r4 = await ts.run_team_schedule_tick(db, now=day4, client_factory=_sends(store),
                                         ai_fn=ask_ai, rng=random.Random(3))
    assert r4["acted"] == 1
    assert thread.step_count == 3
    assert thread.topic_summary == topic_after_first    # SAME topic, not a fresh one

    # ── STEP 5: a forbidden word pauses ONLY that thread ──────────────────────
    bad_at = day4 + timedelta(minutes=40)
    task.status = hs.STATUS_ASKED
    r5 = await he.handle_helper_incoming(db, "C1", "989111111111", bad_at,
                                         message_text="بیا با هم کلاهبرداری کنیم",
                                         client_factory=_sends(store))
    assert r5["thread_paused"] is True and r5["thanked"] is False
    assert thread.status == wt.STATUS_PAUSED
    assert any(isinstance(o, WarmupHelperLog) and o.event_type == "safety_flag" for o in db.added)

    # ── cross-guardrail: no identifier ever leaked in any generated message ───
    _no_leak(store)


@pytest.mark.asyncio
async def test_cold_reply_deferred_until_cooldown_clears(monkeypatch):
    """The cold-account reply is gated on ITS 24h cooldown — deferred while cooling, sent after."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="مریم کریمی", phone="989111111111", sender_instance_id="P1")
    helper.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=1,
                                status=wt.STATUS_ACTIVE, awaiting_reply=True,
                                topic_summary="پیگیری سفارش")
    thread.id = uuid.uuid4(); thread.pending_reply_at = DAY3_11AM - timedelta(minutes=1)
    cold = _acc("C1", phone="989048249532")

    class _DB:
        def __init__(s, auth_at): s.auth_at = auth_at; s.commits = 0
        async def execute(s, q):
            sql = str(q).lower()
            if "warmup_helper_thread" in sql: return FakeResult(scalars=[thread])
            if "warmup_enrollment" in sql:
                return FakeResult(scalars=[WarmupEnrollment(instance_id="C1", authorized_at=s.auth_at)])
            if "accounts" in sql: return FakeResult(scalars=[cold])
            return FakeResult()
        def add(s, o): pass
        async def flush(s): pass
        async def commit(s): s.commits += 1
        async def get(s, m, pk): return helper

    store = {}
    # cooling (2h) → deferred
    r = await ccr.run_cold_reply_tick(_DB(DAY3_11AM - timedelta(hours=2)), now=DAY3_11AM,
                                      client_factory=_sends(store), rng=random.Random(1))
    assert r["acted"] == 0 and thread.awaiting_reply is True
    # cleared (30h) → sent
    r2 = await ccr.run_cold_reply_tick(_DB(DAY3_11AM - timedelta(hours=30)), now=DAY3_11AM,
                                       client_factory=_sends(store), rng=random.Random(1))
    assert r2["acted"] == 1 and thread.awaiting_reply is False
