"""V35 — the «درخواست‌های بی‌پاسخ» (unresponded requests) log filter.

The frontend filter reuses the enriched /warmup-helpers/tasks endpoint, which must now carry the
SENDER (owning account) + Shamsi asked_at/reminded_at so a row can show
contact + sender + cold account + ask time + reminder time + status. This test drives the endpoint
function directly against a fake DB and asserts the enrichment.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.api.v1.warmup_helpers import list_tasks
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask
from app.models.account import AccountStatus


class FakeResult:
    def __init__(self, scalars):
        self._s = list(scalars)
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()


class FakeDB:
    """Routes the three queries list_tasks issues: helpers, accounts, tasks."""
    def __init__(self, helpers, accounts, tasks):
        self.helpers = helpers; self.accounts = accounts; self.tasks = tasks
    async def execute(self, q):
        s = str(q).lower()
        if "warmup_helper_task" in s:
            return FakeResult(self.tasks)
        if "warmup_helper" in s:
            return FakeResult(self.helpers)
        if "accounts" in s:
            return FakeResult(self.accounts)
        return FakeResult([])


def _acc(iid, name):
    return SimpleNamespace(instance_id=iid, name=name, status=AccountStatus.active)


@pytest.mark.asyncio
async def test_tasks_carry_sender_and_shamsi():
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", sender_instance_id="P1")
    helper.id = uuid.uuid4()

    asked = datetime(2026, 5, 4, 8, 30)     # naive UTC
    reminded = datetime(2026, 5, 4, 9, 30)
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1",
                            status="reminded", reminder_count=1)
    task.id = uuid.uuid4(); task.asked_at = asked; task.reminded_at = reminded
    task.done_at = None; task.attempts = 1

    accounts = [_acc("P1", "اکانت اصلی"), _acc("C1", "شماره سرد")]
    db = FakeDB([helper], accounts, [task])

    out = await list_tasks(db=db)
    rows = out["tasks"]
    assert len(rows) == 1
    r = rows[0]
    # sender enrichment (owning account of the contact)
    assert r["sender_instance_id"] == "P1"
    assert r["sender_name"] == "اکانت اصلی"
    assert r["helper_name"] == "رضا محمدی"
    assert r["cold_name"] == "شماره سرد"
    assert r["status"] == "reminded"
    assert r["reminder_count"] == 1
    # Shamsi strings present for asked/reminded (Tehran is UTC+3:30 → 12:00 / 13:00 local)
    assert r["asked_shamsi"] and "12:00" in r["asked_shamsi"]
    assert r["reminded_shamsi"] and "13:00" in r["reminded_shamsi"]
    assert r["asked_shamsi"].startswith("1405/")   # 2026-05-04 → 1405 Shamsi


@pytest.mark.asyncio
async def test_tasks_shamsi_none_when_not_asked():
    helper = WarmupHelper(name="مینا", phone="989122222222", sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status="pending")
    task.id = uuid.uuid4(); task.asked_at = None; task.reminded_at = None
    task.done_at = None; task.attempts = 0; task.reminder_count = 0

    db = FakeDB([helper], [_acc("P1", "اکانت اصلی"), _acc("C1", "سرد")], [task])
    r = (await list_tasks(db=db))["tasks"][0]
    assert r["asked_shamsi"] is None
    assert r["reminded_shamsi"] is None
    assert r["sender_name"] == "اکانت اصلی"
