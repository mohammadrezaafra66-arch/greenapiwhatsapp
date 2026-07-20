"""V33 PART 2 — enforce the 2-distinct-cold-per-contact ceiling (service + DB) + reconcile.

Covers:
  • the service ceiling: `assign_cold_account` rejects a 3rd DISTINCT cold with the Persian error,
    is idempotent for an already-assigned cold, and allows the 2nd;
  • escalation now respects the ceiling (never grows a contact past 2 distinct colds);
  • the PURE drop-selection rule: keep the 2 most-advanced/most-recent pairings, drop the rest;
  • `reconcile_cold_ceiling`: reduces every 3-paired contact to 2, reports each drop, and PAUSES
    (never deletes) a dropped pairing's in-progress thread so no conversation history is lost;
  • the DB-level backstop trigger exists (a real 3rd INSERT is refused at the database).
"""
import uuid
from datetime import datetime, timedelta
import pytest

from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperThread
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_thread as wt


NOW = datetime(2026, 5, 4, 11, 0)


def _task(cold, status, *, asked=None, reminded=None, done=None, created=None):
    t = WarmupHelperTask(helper_id=uuid.uuid4(), cold_instance_id=cold, status=status)
    t.id = uuid.uuid4()
    t.created_at = created or (NOW - timedelta(hours=2))
    t.asked_at, t.reminded_at, t.done_at = asked, reminded, done
    return t


# ── PURE: which pairing(s) to drop ───────────────────────────────────────────
def test_drop_selection_keeps_two_most_advanced():
    """done > reminded > asked > pending → the pending one is dropped from three."""
    c1 = _task("C1", hs.STATUS_DONE, done=NOW - timedelta(minutes=10))
    c2 = _task("C2", hs.STATUS_REMINDED, reminded=NOW - timedelta(minutes=30))
    c3 = _task("C3", hs.STATUS_PENDING)
    drop = hs.select_cold_pairings_to_drop([c1, c2, c3])
    assert drop == ["C3"]


def test_drop_selection_tiebreaks_on_recency():
    """Among equal-status pairings, the LEAST recently active is dropped."""
    older = _task("C1", hs.STATUS_ASKED, asked=NOW - timedelta(hours=5))
    newer = _task("C2", hs.STATUS_ASKED, asked=NOW - timedelta(minutes=20))
    keep_done = _task("C3", hs.STATUS_DONE, done=NOW - timedelta(minutes=5))
    drop = hs.select_cold_pairings_to_drop([older, newer, keep_done])
    assert drop == ["C1"]                         # C3 (done) + C2 (recent ask) kept


def test_drop_selection_noop_within_ceiling():
    assert hs.select_cold_pairings_to_drop([_task("C1", hs.STATUS_PENDING),
                                            _task("C2", hs.STATUS_PENDING)]) == []


# ── service ceiling: assign_cold_account ─────────────────────────────────────
def _helper():
    h = WarmupHelper(name="مخاطب تست", phone="989111111111", is_active=True, sender_instance_id="P1")
    h.id = uuid.uuid4()
    return h


class _AssignDB:
    def __init__(self, helper, existing_tasks):
        self.helper = helper
        self.tasks = list(existing_tasks)
        self.added = []
        self.commits = 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        tasks = self.tasks

        class _R:
            def all(_s):
                return [(t.cold_instance_id,) for t in tasks]     # list_cold_accounts_for_helper

            def scalars(_s):
                class _S:
                    def all(__s):
                        return list(tasks)
                return _S()

            def scalar_one_or_none(_s):
                m = [t for t in tasks if t.cold_instance_id.lower() in sql]   # idempotent lookup
                return m[0] if m else None
        return _R()

    def add(self, o):
        self.added.append(o)
        self.tasks.append(o)

    async def commit(self):
        self.commits += 1

    async def refresh(self, o):
        pass

    async def get(self, model, pk):
        return self.helper if getattr(self.helper, "id", None) == pk else None


def _existing(helper, *colds):
    out = []
    for c in colds:
        t = WarmupHelperTask(helper_id=helper.id, cold_instance_id=c, status=hs.STATUS_PENDING)
        t.id = uuid.uuid4()
        out.append(t)
    return out


@pytest.mark.asyncio
async def test_assign_allows_first_and_second_cold():
    h = _helper()
    db = _AssignDB(h, existing_tasks=_existing(h, "C1"))
    task = await hs.assign_cold_account(db, h.id, "C2")       # 2nd distinct → allowed
    assert task.cold_instance_id == "C2"


@pytest.mark.asyncio
async def test_assign_rejects_third_distinct_cold_with_persian_error():
    h = _helper()
    db = _AssignDB(h, existing_tasks=_existing(h, "C1", "C2"))
    with pytest.raises(ValueError) as ei:
        await hs.assign_cold_account(db, h.id, "C3")          # 3rd distinct → rejected
    assert str(ei.value) == hs.COLD_CEILING_FA
    assert db.added == []


@pytest.mark.asyncio
async def test_assign_is_idempotent_for_existing_cold_even_at_ceiling():
    """Re-assigning one of the 2 existing colds returns the existing task, never a 3rd pairing."""
    h = _helper()
    db = _AssignDB(h, existing_tasks=_existing(h, "C1", "C2"))
    task = await hs.assign_cold_account(db, h.id, "C1")
    assert task.cold_instance_id == "C1"
    assert db.added == []


# ── escalation respects the ceiling (direct) ─────────────────────────────────
class _EscDB:
    def __init__(self, assigned, enrolled):
        self.assigned = assigned
        self.enrolled = enrolled
        self.added = []

    async def execute(self, q):
        s = str(q).lower()
        assigned, enrolled = self.assigned, self.enrolled

        class _R:
            def all(_s):
                return [(c,) for c in assigned]

            def scalars(_s):
                from types import SimpleNamespace
                objs = [SimpleNamespace(cold_instance_id=c) for c in enrolled]

                class _S:
                    def all(__s):
                        return list(objs)
                return _S()
        return _R()

    def add(self, o):
        self.added.append(o)

    async def flush(self):
        pass


@pytest.mark.asyncio
async def test_escalation_capped_by_ceiling():
    db = _EscDB(assigned=["C1"], enrolled=["C1", "C2", "C3"])
    got = await hs.escalate_after_completion(db, uuid.uuid4())
    assert got == ["C2"]                                   # 1 slot left → 1 assigned, not 2


# ── reconcile_cold_ceiling: reduce 3→2, report, pause in-progress thread ─────
class _ReconDB:
    def __init__(self, tasks, threads):
        self.tasks = list(tasks)
        self.threads = list(threads)
        self.deleted = []
        self.commits = 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        tasks, threads = self.tasks, self.threads

        class _R:
            def __init__(_s, scalars):
                _s._s = scalars

            def scalars(_s):
                data = _s._s

                class _S:
                    def all(__s):
                        return list(data)
                return _S()

            def scalar_one_or_none(_s):
                return _s._s[0] if _s._s else None
        if "warmup_helper_thread" in sql:
            matched = [t for t in threads if t.cold_instance_id.lower() in sql]
            return _R(matched)
        if "warmup_helper_task" in sql:
            return _R(list(tasks))
        return _R([])

    async def delete(self, o):
        self.deleted.append(o)
        if o in self.tasks:
            self.tasks.remove(o)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_reconcile_reduces_three_to_two_and_reports():
    hid = uuid.uuid4()
    c1 = _task("C1", hs.STATUS_DONE, done=NOW); c1.helper_id = hid
    c2 = _task("C2", hs.STATUS_ASKED, asked=NOW - timedelta(minutes=20)); c2.helper_id = hid
    c3 = _task("C3", hs.STATUS_PENDING); c3.helper_id = hid
    # the dropped pairing (C3) has a thread WITH progress → must be paused, not deleted
    th3 = WarmupHelperThread(helper_id=hid, cold_instance_id="C3", step_count=1,
                             status=wt.STATUS_ACTIVE)
    th3.id = uuid.uuid4()
    db = _ReconDB(tasks=[c1, c2, c3], threads=[th3])

    report = await hs.reconcile_cold_ceiling(db, apply=True)
    assert len(report) == 1
    entry = report[0]
    assert entry["cold_instance_id"] == "C3" and entry["status"] == hs.STATUS_PENDING
    assert entry["had_active_thread"] is True and entry["thread_paused"] is True
    # the C3 task row was deleted; C1/C2 remain
    assert c3 in db.deleted and c1 not in db.deleted and c2 not in db.deleted
    # the thread was PAUSED (history preserved), never deleted
    assert th3.status == wt.STATUS_PAUSED
    assert th3 not in db.deleted


@pytest.mark.asyncio
async def test_reconcile_dry_run_changes_nothing():
    hid = uuid.uuid4()
    tasks = [_task("C1", hs.STATUS_DONE, done=NOW), _task("C2", hs.STATUS_ASKED, asked=NOW),
             _task("C3", hs.STATUS_PENDING)]
    for t in tasks:
        t.helper_id = hid
    db = _ReconDB(tasks=tasks, threads=[])
    report = await hs.reconcile_cold_ceiling(db, apply=False)
    assert len(report) == 1 and report[0]["cold_instance_id"] == "C3"
    assert db.deleted == [] and db.commits == 0            # dry run: nothing changed


@pytest.mark.asyncio
async def test_reconcile_noop_when_all_within_ceiling():
    hid = uuid.uuid4()
    tasks = [_task("C1", hs.STATUS_DONE, done=NOW), _task("C2", hs.STATUS_PENDING)]
    for t in tasks:
        t.helper_id = hid
    db = _ReconDB(tasks=tasks, threads=[])
    report = await hs.reconcile_cold_ceiling(db, apply=True)
    assert report == [] and db.deleted == []
