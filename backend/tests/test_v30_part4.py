"""V30 PART 4 — completion-based escalation: assign 2 new cold accounts after a success.

Proves:
  • `escalate_after_completion` assigns up to 2 NEW enrolled cold accounts not yet assigned to the
    contact, exactly `min(2, remaining)`, and nothing when the roster is exhausted; it never
    re-assigns already-assigned (completed) cold accounts, and only queues PENDING tasks;
  • it is wired into the completion path (handle_helper_incoming) ONLY for a team-enrolled cold
    account; a non-enrolled completion does not escalate (non-completion keeps its single reminder,
    unchanged — no escalation path touches it).
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from app.services import warmup_helper_service as hs
from app.services import warmup_helper_engine as he
from app.models.warmup_helpers import WarmupHelperTask, WarmupHelper
from app.models.account import AccountStatus


class _EscRes:
    def __init__(self, all_rows=None, scalar_objs=None):
        self._all = all_rows or []; self._scal = scalar_objs or []
    def all(self): return list(self._all)
    def scalars(self):
        objs = self._scal
        class _S:
            def all(self_): return list(objs)
        return _S()


class _EscDB:
    """Serves list_cold_accounts_for_helper (task column rows) + the enrolled-entity query."""
    def __init__(self, assigned, enrolled):
        self.assigned = assigned; self.enrolled = enrolled; self.added = []; self.flushes = 0
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_team_enrollment" in sql:
            return _EscRes(scalar_objs=[SimpleNamespace(cold_instance_id=c) for c in self.enrolled])
        if "warmup_helper_task" in sql:
            return _EscRes(all_rows=[(c,) for c in self.assigned])
        return _EscRes()
    def add(self, o): self.added.append(o)
    async def flush(self): self.flushes += 1


# V33 PART 2 — escalation now RESPECTS the hard 2-distinct-cold ceiling (was: bypassed it). A
# contact with 1 cold can gain at most 1 more (to reach the ceiling of 2); a contact already at 2
# gains nothing. `min(batch, roster_remaining, ceiling_remaining)`.
@pytest.mark.asyncio
async def test_escalate_assigns_only_up_to_ceiling_when_available():
    hid = uuid.uuid4()
    db = _EscDB(assigned=["C1"], enrolled=["C1", "C2", "C3", "C4"])
    new_ids = await hs.escalate_after_completion(db, hid)
    assert new_ids == ["C2"]                            # only 1 more → reaches the 2-cold ceiling
    added = [o for o in db.added if isinstance(o, WarmupHelperTask)]
    assert {t.cold_instance_id for t in added} == {"C2"}
    assert all(t.status == hs.STATUS_PENDING for t in added)   # only queues pending


@pytest.mark.asyncio
async def test_escalate_noop_when_contact_already_at_ceiling():
    hid = uuid.uuid4()
    db = _EscDB(assigned=["C1", "C2", "C3"], enrolled=["C1", "C2", "C3", "C4"])
    new_ids = await hs.escalate_after_completion(db, hid)
    assert new_ids == []                                # already at (past) the ceiling → no growth


@pytest.mark.asyncio
async def test_escalate_noop_when_roster_exhausted():
    hid = uuid.uuid4()
    db = _EscDB(assigned=["C1", "C2"], enrolled=["C1", "C2"])
    new_ids = await hs.escalate_after_completion(db, hid)
    assert new_ids == []
    assert [o for o in db.added if isinstance(o, WarmupHelperTask)] == []
    assert db.flushes == 0                              # nothing to flush


# ── wiring into the completion path ──────────────────────────────────────────
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


class _IncDB:
    def __init__(self, helper, task, sender):
        self.helper = helper; self.task = task; self.sender = sender
        self.added = []; self.commits = 0
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_enrollment" in sql:
            return _Res(rows=[])
        if "warmup_helper_task" in sql:
            return _Res(scalars=[self.task])
        if "warmup_helper" in sql:
            return _Res(scalars=[self.helper])
        if "accounts" in sql:
            return _Res(scalars=[self.sender])
        return _Res()
    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def get(self, model, pk):
        return self.helper if getattr(self.helper, "id", None) == pk else None


def _make(monkeypatch, enrolled_enabled):
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True,
                          sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_ASKED)
    task.id = uuid.uuid4()
    sender = SimpleNamespace(instance_id="P1", api_token="t", phone="989000", name="P1",
                             is_warm_peer=True, status=AccountStatus.active,
                             cooldown_until=None, throttle_until=None, throttle_factor=1.0)
    db = _IncDB(helper, task, sender)

    # Stub the heavy collaborators so the test isolates the escalation wiring.
    thread = SimpleNamespace(id=uuid.uuid4(), status="active", step_count=0,
                             last_step_at=None, awaiting_reply=False, pending_reply_at=None,
                             topic_summary=None)
    monkeypatch.setattr("app.services.warmup_helper_thread.get_or_create_thread",
                        AsyncMock(return_value=thread))
    monkeypatch.setattr("app.services.warmup_thread_safety.scan_and_flag",
                        AsyncMock(return_value=None))
    te = SimpleNamespace(cold_instance_id="C1", is_enabled=enrolled_enabled) if enrolled_enabled is not None else None
    monkeypatch.setattr("app.services.warmup_team_schedule.get_team_enrollment",
                        AsyncMock(return_value=te))
    monkeypatch.setattr(he, "_send_from_main", AsyncMock(return_value="MID"))
    spy = AsyncMock(return_value=["C2", "C3"])
    monkeypatch.setattr(hs, "escalate_after_completion", spy)
    return db, helper, spy


@pytest.mark.asyncio
async def test_completion_escalates_when_cold_is_team_enrolled(monkeypatch):
    db, helper, spy = _make(monkeypatch, enrolled_enabled=True)
    res = await he.handle_helper_incoming(db, "C1", "989111111111",
                                          now=None, message_text="سلام")
    assert res is not None
    spy.assert_awaited_once()
    assert spy.await_args.args[1] == helper.id     # escalated THIS contact


@pytest.mark.asyncio
async def test_completion_does_not_escalate_when_not_enrolled(monkeypatch):
    db, helper, spy = _make(monkeypatch, enrolled_enabled=None)   # no enrollment row
    res = await he.handle_helper_incoming(db, "C1", "989111111111",
                                          now=None, message_text="سلام")
    assert res is not None
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_does_not_escalate_when_enrollment_disabled(monkeypatch):
    db, helper, spy = _make(monkeypatch, enrolled_enabled=False)
    await he.handle_helper_incoming(db, "C1", "989111111111", now=None, message_text="سلام")
    spy.assert_not_awaited()
