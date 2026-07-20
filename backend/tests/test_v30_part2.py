"""V30 PART 2 / V36 PART 2 — per-sender minimum spacing between ASK-requests (now 55 minutes).

Proves:
  • pure `ask_spacing_ok`: no prior ask → allowed; < 55 min → blocked; >= 55 min → allowed;
  • the constraint is keyed per SENDER (last_ask_at_for_sender short-circuits on a missing id);
  • wired into the live team-schedule ask path: a sender that asked < 55 min ago is skipped
    (no send), while the same tick sends once the spacing has elapsed (or the sender never asked);
  • different senders are NOT rate-limited against each other by this rule.

The engine FakeDB harness mirrors tests/test_v29_part7.py (kept self-contained here).
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
from app.services import peer_pacer, send_gate
from app.models.warmup_helpers import (
    WarmupHelper, WarmupHelperTask, WarmupHelperThread, WarmupTeamEnrollment,
)
from app.models.warmup_mesh import WarmupEnrollment
from app.models.account import AccountStatus

NOW = datetime(2026, 5, 4, 11, 0)   # 11:00 Tehran — inside every waking window


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset(); send_gate.clear_live_cache()
    yield
    peer_pacer.reset(); send_gate.clear_live_cache()


# ── pure spacing math ─────────────────────────────────────────────────────────
def test_ask_spacing_ok_thresholds():
    assert spacing.ask_spacing_ok(None, NOW) is True                       # never asked
    assert spacing.ask_spacing_ok(NOW - timedelta(minutes=5), NOW) is False
    assert spacing.ask_spacing_ok(NOW - timedelta(minutes=54, seconds=59), NOW) is False
    assert spacing.ask_spacing_ok(NOW - timedelta(minutes=55), NOW) is True
    assert spacing.ask_spacing_ok(NOW - timedelta(minutes=90), NOW) is True
    assert spacing.ASK_MIN_SPACING_MINUTES == 55


def test_two_asks_same_sender_are_55min_apart():
    # First ask allowed at NOW; the next is blocked until NOW+55m, allowed at/after it.
    first = NOW
    assert spacing.ask_spacing_ok(None, first) is True
    assert spacing.ask_spacing_ok(first, first + timedelta(minutes=30)) is False
    assert spacing.ask_spacing_ok(first, first + timedelta(minutes=55)) is True


def test_different_senders_independent_pure():
    # Sender A asked 5 min ago (blocked); sender B never asked (allowed). Same instant.
    last_by_sender = {"A": NOW - timedelta(minutes=5), "B": None}
    assert spacing.ask_spacing_ok(last_by_sender["A"], NOW) is False
    assert spacing.ask_spacing_ok(last_by_sender["B"], NOW) is True


@pytest.mark.asyncio
async def test_last_ask_at_for_sender_missing_id_short_circuits():
    db = AsyncMock()
    assert await spacing.last_ask_at_for_sender(db, None) is None
    db.execute.assert_not_awaited()


# ── engine fake (mirrors test_v29_part7) ─────────────────────────────────────
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
            return FakeResult(scalars=[e for e in self.enrolls if e.is_enabled])
        if "warmup_enrollment" in sql:
            if "instance_id =" in sql:
                return FakeResult(scalars=[self.mesh_enr] if self.mesh_enr else [])
            return FakeResult(rows=[(self.mesh_enr.instance_id, self.mesh_enr.state, True)]
                              if self.mesh_enr else [])
        if "warmup_sender_config" in sql:
            return FakeResult(scalars=[])
        if "outreach_brief" in sql:
            return FakeResult(scalars=[])
        if "warmup_helper_thread" in sql:
            return FakeResult(scalars=list(self.threads))
        if "warmup_helper_task" in sql:
            if "select warmup_helper_task.helper_id" in sql:
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


def _setup(sender_id="P1"):
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id=sender_id, job_title="کارشناس", years_experience=5)
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status="pending")
    task.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=0,
                                status=wt.STATUS_ACTIVE)
    thread.id = uuid.uuid4()
    te = WarmupTeamEnrollment(cold_instance_id="C1", is_enabled=True,
                              enrolled_at=NOW - timedelta(days=3), day_index=0)
    mesh = WarmupEnrollment(instance_id="C1", state="RECEIVING",
                            authorized_at=NOW - timedelta(hours=30))   # cooldown cleared
    cold = _acc("C1"); cold.phone = "989048249532"
    sender = _acc(sender_id, warm=True)
    db = FakeDB(enrolls=[te], accounts=[cold, sender], mesh_enr=mesh,
                helpers=[helper], tasks=[task], threads=[thread])
    return db, helper, thread, te


async def _ai(*, name, topic, step_count, brief, profile_line):
    return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک داشتم 🙏"


@pytest.mark.asyncio
async def test_team_tick_blocks_ask_within_spacing(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(spacing, "last_ask_at_for_sender",
                        AsyncMock(return_value=NOW - timedelta(minutes=5)))
    db, helper, thread, te = _setup()
    store = {}
    res = await ts.run_team_schedule_tick(db, now=NOW, client_factory=_factory(store),
                                          ai_fn=_ai, rng=random.Random(1))
    assert res["acted"] == 0
    assert "phone" not in store            # spacing gate suppressed the ask
    assert thread.step_count == 0


@pytest.mark.asyncio
async def test_team_tick_sends_after_55min(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(spacing, "last_ask_at_for_sender",
                        AsyncMock(return_value=NOW - timedelta(minutes=60)))
    db, helper, thread, te = _setup()
    store = {}
    res = await ts.run_team_schedule_tick(db, now=NOW, client_factory=_factory(store),
                                          ai_fn=_ai, rng=random.Random(2))
    assert res["acted"] == 1 and res["sent"] is True
    assert store["phone"] == "989111111111"
    assert thread.step_count == 1


@pytest.mark.asyncio
async def test_team_tick_sends_when_never_asked(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(spacing, "last_ask_at_for_sender", AsyncMock(return_value=None))
    db, helper, thread, te = _setup()
    store = {}
    res = await ts.run_team_schedule_tick(db, now=NOW, client_factory=_factory(store),
                                          ai_fn=_ai, rng=random.Random(3))
    assert res["acted"] == 1 and res["sent"] is True


@pytest.mark.asyncio
async def test_cross_sender_independence_in_tick(monkeypatch):
    # Keyed by sender: P1 asked 5 min ago (blocked), P2 never asked (allowed).
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    async def _keyed(db, sid):
        return NOW - timedelta(minutes=5) if sid == "P1" else None
    monkeypatch.setattr(spacing, "last_ask_at_for_sender", AsyncMock(side_effect=_keyed))

    # P1 is blocked → no send.
    db1, _, thread1, _ = _setup(sender_id="P1")
    s1 = {}
    r1 = await ts.run_team_schedule_tick(db1, now=NOW, client_factory=_factory(s1),
                                         ai_fn=_ai, rng=random.Random(4))
    assert r1["acted"] == 0 and "phone" not in s1

    # P2, same instant, is NOT blocked → sends. Proves the rule is per-sender.
    db2, _, thread2, _ = _setup(sender_id="P2")
    s2 = {}
    r2 = await ts.run_team_schedule_tick(db2, now=NOW, client_factory=_factory(s2),
                                         ai_fn=_ai, rng=random.Random(5))
    assert r2["acted"] == 1 and s2.get("phone") == "989111111111"
