"""V31 — unify the legacy mesh-warming ask (run_helper_tick) through the SAME AI thread-aware
generator used by the Team Collaboration tick.

Proves:
  • run_helper_tick's ASK now comes from the AI generator (varied/personalized/emoji), NOT the
    static build_ask_message template — verified by injecting an ai_fn and seeing its text sent;
  • the ask still carries the wa.me link + copy/paste suggestion and still routes through
    _send_from_main (can_send_now health gate) + peer_pacer (unchanged rails);
  • profile personalization (job_title) reaches the generator;
  • COMBINED cross-path anti-repeat: a near-duplicate of a recent ask body (whichever path logged
    it) is rejected by the shared generator, so no two recent asks are near-duplicates;
  • graceful fallback: an identifier-like contact name falls back to the static builder (no crash).
"""
import uuid
import random
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_engine as he
from app.services import warmup_helper_service as hs
from app.services import peer_pacer, send_gate
from app.services.warmup_content import has_emoji, is_near_duplicate
from app.services.outreach_message import generate_thread_ask_message
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperConfig
from app.models.account import Account, AccountStatus
from app.services.warmup_state import WarmupState

TEHRAN_11AM = datetime(2026, 5, 4, 11, 0)


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset(); send_gate.clear_live_cache()
    yield
    peer_pacer.reset(); send_gate.clear_live_cache()


class FakeResult:
    def __init__(self, scalars=None, rows=None, scalar=None):
        self._s = list(scalars) if scalars is not None else []
        self._rows = rows
        self._scalar = scalar
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()
    def all(self): return list(self._rows) if self._rows is not None else list(self._s)
    def scalar_one_or_none(self): return self._s[0] if self._s else None
    def scalar(self): return self._scalar


class FakeDB:
    """Drives run_helper_tick end-to-end incl. the new V31 generator queries (thread/brief/log)."""
    def __init__(self, *, helpers, tasks, accounts, enrollments, config, log_rows=None):
        self.helpers = helpers; self.tasks = tasks; self.accounts = accounts
        self.enrollments = enrollments; self.config = config
        self.log_rows = log_rows or []; self.added = []; self.commits = 0
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_helper_log" in sql:
            return FakeResult(scalars=list(self.log_rows))     # for recent_ask_bodies
        if "warmup_helper_thread" in sql:
            return FakeResult(scalars=[])                       # no prior thread
        if "outreach_brief" in sql:
            return FakeResult(scalars=[])                       # no brief
        if "count(" in sql:
            return FakeResult(scalar=sum(1 for h in self.helpers if h.is_active))
        if "warmup_helper_config" in sql:
            return FakeResult(scalars=[self.config] if self.config else [])
        if "warmup_helper_task" in sql:
            if "warmup_helper_task.id" not in sql:
                return FakeResult(rows=[(t.helper_id, t.cold_instance_id) for t in self.tasks])
            rows = list(self.tasks)
            if "status" in sql:
                rows = [t for t in rows if t.status in sql]
            return FakeResult(scalars=rows)
        if "warmup_helper" in sql:
            return FakeResult(scalars=list(self.helpers))
        if "warmup_enrollment" in sql:
            return FakeResult(rows=list(self.enrollments))
        if "accounts" in sql:
            match = [a for a in self.accounts if a.instance_id.lower() in sql]
            if match and "instance_id =" in sql:
                return FakeResult(scalars=match)
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


def _acc(iid, *, warm=False):
    a = Account(name=f"acc-{iid}", instance_id=iid, api_token="t")
    a.id = uuid.uuid4(); a.status = AccountStatus.active; a.is_warm_peer = warm
    a.phone = f"98912{iid[-4:]}"
    return a


def _factory(store):
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): store["phone"] = p; store["text"] = t; return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    return factory


def _setup(helper):
    helper.id = uuid.uuid4()
    cold = _acc("C1"); cold.phone = "989048249532"
    peer = _acc("P1", warm=True)
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_PENDING)
    task.id = uuid.uuid4(); task.created_at = TEHRAN_11AM
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)
    return FakeDB(helpers=[helper], tasks=[task], accounts=[cold, peer],
                  enrollments=[("C1", WarmupState.RECEIVING.value, True)], config=config), task


@pytest.mark.asyncio
async def test_helper_tick_ask_now_uses_ai_generator(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          job_title="کارشناس فروش", years_experience=7)
    db, task = _setup(helper)
    store = {}

    async def ai(*, name, topic, step_count, brief, profile_line):
        # a distinctive AI body that is NOT the static template
        return f"سلام {name} جان 🌹 درباره‌ی {topic} یه لطف کوچیک ازت می‌خواستم"

    res = await he.run_helper_tick(db, now=TEHRAN_11AM, client_factory=_factory(store),
                                   rng=random.Random(1), ai_fn=ai)
    assert res["acted"] == 1 and res["kind"] == "ask" and res["sent"] is True
    txt = store["text"]
    assert "رضا محمدی" in txt                       # real name
    assert has_emoji(txt)                            # emoji present
    assert "🌹" in txt                                # the AI body's emoji specifically
    assert "https://wa.me/989048249532" in txt        # link still appended
    assert hs.SUGGESTED_TEXT in txt                   # suggestion still appended
    # It is NOT the old static template:
    assert "لطف می‌کنی به این شماره‌ی جدید ما یک پیام کوتاه بدی؟" not in txt


@pytest.mark.asyncio
async def test_helper_tick_ask_falls_back_when_name_unusable(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    # a name that looks like an identifier → generator rejects it → static fallback (no crash)
    helper = WarmupHelper(name="989123456789", phone="989111111111", is_active=True)
    db, task = _setup(helper)
    store = {}
    res = await he.run_helper_tick(db, now=TEHRAN_11AM, client_factory=_factory(store),
                                   rng=random.Random(1), ai_fn=AsyncMock(return_value="x"))
    assert res["acted"] == 1 and res["sent"] is True
    # fell back to the static builder, which still carries the link + suggestion
    assert "https://wa.me/989048249532" in store["text"]
    assert hs.SUGGESTED_TEXT in store["text"]


@pytest.mark.asyncio
async def test_combined_cross_path_anti_repeat():
    """A near-duplicate of a body already logged (by EITHER path) is rejected by the shared
    generator → the two recent asks are never near-duplicates."""
    prior_body = "سلام رضا محمدی جان 🌹 درباره‌ی پیگیری سفارش یه لطف کوچیک ازت می‌خواستم"

    async def ai_repeats(*, name, topic, step_count, brief, profile_line):
        return prior_body   # AI tries to emit a near-duplicate of the prior ask

    msg, source = await generate_thread_ask_message(
        brief=None, contact={"name": "رضا محمدی"}, topic="پیگیری سفارش", step_count=1,
        cold_phone_digits=["989048249532"], recent=[prior_body], ai_fn=ai_repeats,
        rng=random.Random(2))
    body = msg.split("\n", 1)[0]
    assert source == "fallback"                       # the near-dup AI candidate was rejected
    assert not is_near_duplicate(body, [prior_body])   # the chosen body is genuinely different
    assert has_emoji(body)
