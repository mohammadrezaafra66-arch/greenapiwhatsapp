"""V33 PART 3 — clean orphaned warmup_helper_task rows + prevent recurrence.

Covers:
  • `cleanup_orphan_helper_tasks` removes task AND thread rows whose helper_id points to a deleted
    contact, and leaves valid rows untouched, reporting exactly what was removed;
  • `delete_helper` REFUSES to delete a contact that still has ACTIVE (in-flight) tasks, with a clear
    Persian message (so a delete can never strand in-flight tasks);
  • a contact with only terminal tasks (done/skipped) — or none — is deletable.
The DB-level FK (ON DELETE CASCADE) backstop is exercised live against Postgres (see the PART 3
report), not in these pure unit tests.
"""
import uuid
import pytest

from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperThread
from app.services import warmup_helper_service as hs


def _helper():
    h = WarmupHelper(name="مخاطب تست", phone="989111111111", is_active=True, sender_instance_id="P1")
    h.id = uuid.uuid4()
    return h


def _task(hid, cold, status):
    t = WarmupHelperTask(helper_id=hid, cold_instance_id=cold, status=status)
    t.id = uuid.uuid4()
    return t


def _thread(hid, cold):
    th = WarmupHelperThread(helper_id=hid, cold_instance_id=cold, step_count=0)
    th.id = uuid.uuid4()
    return th


# ── cleanup_orphan_helper_tasks ──────────────────────────────────────────────
class _CleanupDB:
    def __init__(self, helpers, tasks, threads):
        self.helpers = list(helpers)
        self.tasks = list(tasks)
        self.threads = list(threads)
        self.deleted = []
        self.commits = 0

    async def execute(self, q):
        sql = str(q).lower()
        helpers, tasks, threads = self.helpers, self.tasks, self.threads

        class _R:
            def all(_s):
                return [(h.id,) for h in helpers]          # select(WarmupHelper.id)

            def scalars(_s):
                data = threads if "warmup_helper_thread" in sql else tasks

                class _S:
                    def all(__s):
                        return list(data)
                return _S()
        return _R()

    async def delete(self, o):
        self.deleted.append(o)
        if o in self.tasks:
            self.tasks.remove(o)
        if o in self.threads:
            self.threads.remove(o)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_cleanup_removes_orphans_keeps_valid():
    live = _helper()
    dead_id = uuid.uuid4()                                  # a contact that no longer exists
    good_task = _task(live.id, "C1", hs.STATUS_PENDING)
    orphan_t1 = _task(dead_id, "C1", hs.STATUS_ASKED)
    orphan_t2 = _task(dead_id, "C2", hs.STATUS_ASKED)
    good_thread = _thread(live.id, "C1")
    orphan_th = _thread(dead_id, "C1")
    db = _CleanupDB(helpers=[live], tasks=[good_task, orphan_t1, orphan_t2],
                    threads=[good_thread, orphan_th])

    report = await hs.cleanup_orphan_helper_tasks(db)
    assert len(report["tasks_removed"]) == 2
    assert {r["cold_instance_id"] for r in report["tasks_removed"]} == {"C1", "C2"}
    assert all(r["helper_id"] == str(dead_id) for r in report["tasks_removed"])
    assert len(report["threads_removed"]) == 1
    # valid rows survive, orphans deleted
    assert good_task not in db.deleted and good_thread not in db.deleted
    assert orphan_t1 in db.deleted and orphan_t2 in db.deleted and orphan_th in db.deleted


@pytest.mark.asyncio
async def test_cleanup_noop_when_no_orphans():
    live = _helper()
    db = _CleanupDB(helpers=[live], tasks=[_task(live.id, "C1", hs.STATUS_DONE)],
                    threads=[_thread(live.id, "C1")])
    report = await hs.cleanup_orphan_helper_tasks(db)
    assert report == {"tasks_removed": [], "threads_removed": []}
    assert db.deleted == [] and db.commits == 0


# ── delete_helper guard ──────────────────────────────────────────────────────
class _DeleteDB:
    def __init__(self, helper, active_count):
        self.helper = helper
        self.active_count = active_count
        self.deleted = []
        self.commits = 0

    async def execute(self, q):
        cnt = self.active_count

        class _R:
            def scalar(_s):
                return cnt
        return _R()

    async def get(self, model, pk):
        return self.helper if getattr(self.helper, "id", None) == pk else None

    async def delete(self, o):
        self.deleted.append(o)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_delete_rejected_when_active_tasks_exist():
    h = _helper()
    db = _DeleteDB(h, active_count=2)
    with pytest.raises(ValueError) as ei:
        await hs.delete_helper(db, h.id)
    assert str(ei.value) == hs.DELETE_BLOCKED_ACTIVE_FA
    assert db.deleted == []                                  # contact NOT deleted


@pytest.mark.asyncio
async def test_delete_allowed_when_no_active_tasks():
    h = _helper()
    db = _DeleteDB(h, active_count=0)                        # only terminal/none
    ok = await hs.delete_helper(db, h.id)
    assert ok is True and h in db.deleted


@pytest.mark.asyncio
async def test_delete_missing_helper_returns_false():
    db = _DeleteDB(_helper(), active_count=0)
    ok = await hs.delete_helper(db, uuid.uuid4())            # different id → not found
    assert ok is False and db.deleted == []
