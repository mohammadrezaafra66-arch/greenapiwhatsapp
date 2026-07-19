"""V33 PART 1 — fix the confirmed root cause of tasks stuck `pending`.

Confirmed root cause (investigated against live data + code + runtime, not assumed):
`ensure_helper_tasks` fanned every active contact out to EVERY cold number being warmed at once
(31 contacts × 3 warmed colds = 93 tasks — every contact pinned to all 3). That
  (a) violated the intended ≤2-cold-per-contact ceiling, and
  (b) inflated the ask queue far past what the deliberately-slow, single-sender anti-ban pacing
      (≤1 ask / 20 min) can ever drain — AND it regenerated the excess on every tick, so `pending`
      was structurally undrainable and looked permanently "stuck".
No individual gate was broken: the global toggle was ON, the 09–19 window + 20-min spacing + pacer
all released normally, and the ticks ran without swallowed exceptions. The fix bounds the fan-out to
the same `MAX_COLD_ACCOUNTS_PER_CONTACT` ceiling `assign_cold_account` enforces, counting a contact's
existing pairings toward that budget — so the queue is bounded and drainable, and a `pending` task
still progresses to `asked` inside the send window.
"""
import uuid
import random
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.models.account import Account, AccountStatus
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperConfig
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_engine as he
from app.services import peer_pacer
from app.services.warmup_state import WarmupState


TEHRAN_11AM = datetime(2026, 5, 4, 11, 0)   # inside both the 09–21 and 09–19 windows


@pytest.fixture(autouse=True)
def _reset_pacer():
    peer_pacer.reset()
    yield
    peer_pacer.reset()


# ── minimal fake for ensure_helper_tasks (returns existing pairs, captures adds) ──
class _EnsureDB:
    def __init__(self, existing_pairs):
        self._pairs = list(existing_pairs)   # list[(helper_id, cold_instance_id)]
        self.added = []

    async def execute(self, q):
        pairs = self._pairs

        class _R:
            def all(_s):
                return list(pairs)
        return _R()

    def add(self, o):
        self.added.append(o)
        self._pairs.append((o.helper_id, o.cold_instance_id))

    async def flush(self):
        pass


def _helper(name="مخاطب تست", sid="P1"):
    h = WarmupHelper(name=name, phone="989111111111", is_active=True, sender_instance_id=sid)
    h.id = uuid.uuid4()
    return h


# ── the fan-out cap: the actual stall fix (fail-before / pass-after) ─────────────
@pytest.mark.asyncio
async def test_fanout_capped_at_cold_ceiling_not_every_warmed_cold():
    """A fresh contact + 3 warmed colds → exactly 2 pairings (the ceiling), NOT 3 (the old stall)."""
    h = _helper()
    db = _EnsureDB(existing_pairs=[])
    created = await he.ensure_helper_tasks(db, ["C1", "C2", "C3"], [h])
    assert created == hs.MAX_COLD_ACCOUNTS_PER_CONTACT == 2
    assert len({t.cold_instance_id for t in db.added}) == 2
    assert all(isinstance(t, WarmupHelperTask) and t.status == hs.STATUS_PENDING for t in db.added)


@pytest.mark.asyncio
async def test_fanout_never_exceeds_ceiling_for_contact_already_at_it():
    """A contact already paired to 2 colds gets NO new auto-pairing — the queue can't re-inflate."""
    h = _helper()
    db = _EnsureDB(existing_pairs=[(h.id, "C1"), (h.id, "C2")])
    created = await he.ensure_helper_tasks(db, ["C1", "C2", "C3"], [h])
    assert created == 0
    assert db.added == []


@pytest.mark.asyncio
async def test_fanout_tops_up_existing_toward_ceiling_only():
    """A contact with 1 existing cold + 3 warmed → exactly 1 new pairing (reaching, not passing, 2)."""
    h = _helper()
    db = _EnsureDB(existing_pairs=[(h.id, "C1")])
    created = await he.ensure_helper_tasks(db, ["C1", "C2", "C3"], [h])
    assert created == 1
    assert db.added[0].cold_instance_id in {"C2", "C3"}


@pytest.mark.asyncio
async def test_fanout_idempotent_for_existing_pair():
    """Re-running with an already-present pair (under the ceiling) creates nothing new for it."""
    h = _helper()
    db = _EnsureDB(existing_pairs=[(h.id, "C1")])
    created = await he.ensure_helper_tasks(db, ["C1"], [h])
    assert created == 0


# ── forward progress: a pending task still reaches `asked` in the send window ────
class _TickDB:
    """Routes the queries run_helper_tick issues, reproducing an over-paired backlog on one sender."""
    def __init__(self, helpers, tasks, accounts, enrollments, config):
        self.helpers = list(helpers)
        self.tasks = list(tasks)
        self.accounts = list(accounts)
        self.enrollments = list(enrollments)   # (instance_id, state, is_enabled)
        self.config = config
        self.added = []
        self.commits = 0

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
                data = _s._s

                class _S:
                    def all(__s):
                        return list(data)
                return _S()

            def all(_s):
                return list(_s._rows)

            def scalar_one_or_none(_s):
                return _s._s[0] if _s._s else None

            def scalar(_s):
                return len(_s._s)
        if "warmup_helper_config" in sql:
            return _R(scalars=[self.config] if self.config else [])
        if "warmup_helper_thread" in sql:
            return _R(scalars=[])                       # no thread → generic topic / static fallback
        if "outreach_brief" in sql:
            return _R(scalars=[])
        if "warmup_helper_log" in sql:
            return _R(scalars=[], rows=[])
        if "warmup_helper_task" in sql:
            if "warmup_helper_task.id" not in sql:      # ensure_helper_tasks pair select
                return _R(rows=[(t.helper_id, t.cold_instance_id) for t in self.tasks])
            rows = list(self.tasks)
            if "status in" in sql or "status =" in sql:
                rows = [t for t in rows if t.status in sql]
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return _R(scalars=rows)
        if "warmup_helper" in sql:                      # WarmupHelper entity/list (checked last)
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
async def test_pending_task_progresses_to_asked_in_window(monkeypatch):
    """The 'stuck' backlog scenario: a contact over-paired to 3 colds with several pending tasks on a
    single sender. One run of the tick (inside 09–19, gate open) still advances a pending task to
    `asked` — proving the loop is not stuck; it drains, now over a BOUNDED queue."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    sender = _acc("P1", warm=True)
    cold = _acc("C1", phone="989048249532")
    helper = _helper(sid="P1")
    # Over-paired backlog: 3 pending tasks for the same contact (the exact violation from prod).
    pend = []
    for cid in ("C1", "C2", "C3"):
        t = WarmupHelperTask(helper_id=helper.id, cold_instance_id=cid, status=hs.STATUS_PENDING)
        t.id = uuid.uuid4()
        t.created_at = TEHRAN_11AM - timedelta(minutes=30)
        pend.append(t)
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)   # gate open
    # Only C1 is actually being warmed (so it's the eligible cold for run_helper_tick).
    db = _TickDB(helpers=[helper], tasks=pend, accounts=[sender, cold],
                 enrollments=[("C1", WarmupState.RECEIVING.value, True)], config=config)

    sent = {}

    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)

        async def _send(phone, text):
            sent["phone"] = phone
            sent["text"] = text
            return "MID1"
        c.send_message = AsyncMock(side_effect=_send)
        return c

    res = await he.run_helper_tick(db, now=TEHRAN_11AM, client_factory=factory,
                                   rng=random.Random(1))
    assert res["enabled"] and res["acted"] == 1 and res["kind"] == "ask"
    assert res["sent"] is True
    # the C1 pending task advanced to asked, stamped at the tick's `now` (within the window)
    c1 = next(t for t in pend if t.cold_instance_id == "C1")
    assert c1.status == hs.STATUS_ASKED and c1.asked_at == TEHRAN_11AM
    assert sent["phone"] == helper.phone
