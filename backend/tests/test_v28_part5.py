"""V28 PART 5 — outreach dashboard.

Proves the per-sender dashboard reports:
  • correct per-sender contact counts (lists don't mix between senders);
  • the soft-warning banner when a sender's list is over threshold, none when under;
  • per-contact task statuses (pending/asked/reminded/done) per cold number;
  • a per-status summary;
  • the sender role labeled INDEPENDENTLY of mesh warm-peer status.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.services import warmup_helper_service as hs
from app.services.warmup_helper_service import assemble_outreach_dashboard, SENDER_ROLE_NOTE


def _acct(iid, warm=False):
    return SimpleNamespace(instance_id=iid, name=f"acct-{iid}", is_warm_peer=warm)


def _helper(name, sender, active=True):
    h = SimpleNamespace(id=uuid.uuid4(), name=name, phone="9891", sender_instance_id=sender,
                        is_active=active)
    return h


def _task(helper_id, cold, status, **kw):
    return SimpleNamespace(helper_id=helper_id, cold_instance_id=cold, status=status,
                           asked_at=kw.get("asked_at"), reminded_at=kw.get("reminded_at"),
                           done_at=kw.get("done_at"))


# ── per-sender counts don't mix ──────────────────────────────────────────────
def test_counts_are_per_sender():
    a1, a2 = _acct("S1"), _acct("S2")
    h1 = _helper("رضا", "S1")
    h2 = _helper("مریم", "S1")
    h3 = _helper("علی", "S2")
    board = assemble_outreach_dashboard([a1, a2], [h1, h2, h3], [], threshold=30)
    by = {s["instance_id"]: s for s in board}
    assert by["S1"]["contact_count"] == 2
    assert by["S2"]["contact_count"] == 1
    assert {c["name"] for c in by["S1"]["contacts"]} == {"رضا", "مریم"}   # lists don't mix


# ── soft-warning banner ──────────────────────────────────────────────────────
def test_soft_warning_over_threshold():
    a = _acct("S1")
    helpers = [_helper(f"c{i}", "S1") for i in range(31)]
    board = assemble_outreach_dashboard([a], helpers, [], threshold=30)
    assert board[0]["contact_count"] == 31
    assert board[0]["soft_warning"] is not None       # banner shown

    board2 = assemble_outreach_dashboard([a], helpers[:30], [], threshold=30)
    assert board2[0]["soft_warning"] is None          # exactly at threshold → no banner


# ── per-contact task statuses + summary ──────────────────────────────────────
def test_task_statuses_and_summary():
    a = _acct("S1")
    h = _helper("رضا", "S1")
    tasks = [
        _task(h.id, "C1", hs.STATUS_ASKED, asked_at=datetime(2026, 7, 1, 10)),
        _task(h.id, "C2", hs.STATUS_DONE, done_at=datetime(2026, 7, 1, 11)),
        _task(h.id, "C3", hs.STATUS_PENDING),
    ]
    board = assemble_outreach_dashboard([a], [h], tasks, threshold=30)
    s = board[0]
    assert s["status_summary"][hs.STATUS_ASKED] == 1
    assert s["status_summary"][hs.STATUS_DONE] == 1
    assert s["status_summary"][hs.STATUS_PENDING] == 1
    contact = s["contacts"][0]
    statuses = {t["cold_instance_id"]: t["status"] for t in contact["tasks"]}
    assert statuses == {"C1": "asked", "C2": "done", "C3": "pending"}
    # asked_at is serialized
    c1 = next(t for t in contact["tasks"] if t["cold_instance_id"] == "C1")
    assert c1["asked_at"] == "2026-07-01T10:00:00"


# ── role independent of warm-peer status ─────────────────────────────────────
def test_sender_role_independent_of_warm_peer():
    warm = _acct("W", warm=True)     # is a mesh warm peer AND used as a sender
    plain = _acct("P", warm=False)   # not a warm peer, still a valid sender
    board = assemble_outreach_dashboard([warm, plain], [_helper("x", "W"), _helper("y", "P")], [])
    by = {s["instance_id"]: s for s in board}
    assert by["W"]["is_warm_peer"] is True
    assert by["P"]["is_warm_peer"] is False
    assert all(s["role_note"] == SENDER_ROLE_NOTE for s in board)   # both labeled clearly


# ── async wrapper via a fake DB ──────────────────────────────────────────────
class _Scalars:
    def __init__(self, items): self._i = list(items)
    def all(self): return list(self._i)


class _Result:
    def __init__(self, scalars=None): self._s = scalars or []
    def scalars(self): return _Scalars(self._s)
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class _DB:
    def __init__(self, results): self._r = list(results)
    async def execute(self, *a, **k): return self._r.pop(0) if self._r else _Result()
    async def commit(self): pass


@pytest.mark.asyncio
async def test_build_outreach_dashboard_wrapper():
    a = _acct("S1")
    h = _helper("رضا", "S1")
    cfg = SimpleNamespace(is_enabled=True, soft_warning_threshold=30)
    # order: accounts, list_helpers, tasks, get_config(threshold)
    db = _DB([_Result(scalars=[a]), _Result(scalars=[h]), _Result(scalars=[]),
              _Result(scalars=[cfg])])
    out = await hs.build_outreach_dashboard(db)
    assert out["threshold"] == 30
    assert out["senders"][0]["instance_id"] == "S1"
    assert out["senders"][0]["contact_count"] == 1
