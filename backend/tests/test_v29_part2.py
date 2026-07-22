"""V29 PART 2 «همکاری تیمی» — roster + mapping (rich profile, ≤2 cold-account ceiling,
per-sender toggle).

Proves:
  • a contact can be assigned to 1 then a 2nd cold account, but a 3rd is rejected with the
    Persian ceiling message;
  • re-assigning an already-linked cold account is idempotent (no duplicate, no error);
  • unassigning removes the pairing;
  • the per-sender toggle persists independently;
  • full-name enforcement is active on the V29 boundary path.
"""
import uuid
import pytest

from app.services import warmup_helper_service as hs
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupSenderConfig


class _Scalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class _Result:
    def __init__(self, scalars=None, rows=None, scalar=None):
        self._scalars = list(scalars) if scalars is not None else []
        self._rows = rows
        self._scalar = scalar
    def scalars(self): return _Scalars(self._scalars)
    def scalar(self): return self._scalar
    def all(self): return list(self._rows) if self._rows is not None else list(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class _DB:
    def __init__(self, results=None, helper=None):
        self._results = list(results or [])
        self._helper = helper
        self.added = []
        self.deleted = []
        self.commits = 0
    async def execute(self, *a, **k):
        return self._results.pop(0) if self._results else _Result()
    def add(self, o): self.added.append(o)
    async def delete(self, o): self.deleted.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, o):
        if getattr(o, "id", None) is None:
            o.id = uuid.uuid4()
    async def get(self, model, pk): return self._helper


def _helper():
    h = WarmupHelper(name="رضا محمدی", phone="989120000001", sender_instance_id="S1")
    h.id = uuid.uuid4()
    return h


# ── ceiling of 2 ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_assign_first_cold_account():
    h = _helper()
    db = _DB(results=[_Result(rows=[])], helper=h)   # no existing assignments
    task = await hs.assign_cold_account(db, h.id, "COLD-1")
    assert task.cold_instance_id == "COLD-1" and task.status == hs.STATUS_PENDING
    assert db.commits >= 1


@pytest.mark.asyncio
async def test_assign_second_cold_account_ok():
    h = _helper()
    db = _DB(results=[_Result(rows=[("COLD-1",)])], helper=h)  # already has 1
    task = await hs.assign_cold_account(db, h.id, "COLD-2")
    assert task.cold_instance_id == "COLD-2"


@pytest.mark.asyncio
async def test_assign_third_cold_account_rejected():
    h = _helper()
    db = _DB(results=[_Result(rows=[("COLD-1",), ("COLD-2",)])], helper=h)  # already 2
    with pytest.raises(ValueError) as e:
        await hs.assign_cold_account(db, h.id, "COLD-3")
    assert "۲ اکانت سرد" in str(e.value)      # Persian ceiling message
    assert db.commits == 0                     # nothing committed


@pytest.mark.asyncio
async def test_assign_duplicate_is_idempotent():
    h = _helper()
    existing = WarmupHelperTask(helper_id=h.id, cold_instance_id="COLD-1", status=hs.STATUS_ASKED)
    existing.id = uuid.uuid4()
    db = _DB(results=[_Result(rows=[("COLD-1",)]), _Result(scalars=[existing])], helper=h)
    task = await hs.assign_cold_account(db, h.id, "COLD-1")
    assert task is existing               # returns the existing pairing, no duplicate added
    assert existing not in db.added


@pytest.mark.asyncio
async def test_assign_unknown_helper_rejected():
    db = _DB(results=[], helper=None)
    with pytest.raises(ValueError) as e:
        await hs.assign_cold_account(db, uuid.uuid4(), "COLD-1")
    assert "یافت نشد" in str(e.value)


# ── unassign ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_unassign_removes_pairing():
    h = _helper()
    t1 = WarmupHelperTask(helper_id=h.id, cold_instance_id="COLD-1")
    db = _DB(results=[_Result(scalars=[t1])])
    removed = await hs.unassign_cold_account(db, h.id, "COLD-1")
    assert removed == 1 and t1 in db.deleted and db.commits >= 1


# ── list / count ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_and_count_distinct():
    h = _helper()
    db = _DB(results=[_Result(rows=[("COLD-1",), ("COLD-1",), ("COLD-2",)])])
    lst = await hs.list_cold_accounts_for_helper(db, h.id)
    assert lst == ["COLD-1", "COLD-2"]     # de-duplicated, order preserved
    db2 = _DB(results=[_Result(rows=[("COLD-1",), ("COLD-2",)])])
    assert await hs.count_cold_accounts_for_helper(db2, h.id) == 2


# ── per-sender toggle persists ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sender_toggle_persists():
    cfg = WarmupSenderConfig(sender_instance_id="S1", is_enabled=True)
    db = _DB(results=[_Result(scalars=[cfg])])
    out = await hs.set_sender_enabled(db, "S1", False)
    assert out.is_enabled is False and db.commits >= 1


@pytest.mark.asyncio
async def test_enabled_sender_ids_returns_disabled():
    class _RowsDB(_DB):
        async def execute(self, *a, **k):
            return _Result(rows=[("S1", True), ("S2", False), ("S3", False)])
    ids = await hs.enabled_sender_ids(_RowsDB())
    assert ids == {"S2", "S3"}


# ── full-name enforcement at the boundary ─────────────────────────────────────
@pytest.mark.asyncio
async def test_full_name_required_via_service_flag():
    with pytest.raises(ValueError):
        await hs.add_helper(_DB(), "رضا", "989120000001", sender_instance_id="S1",
                            require_full_name=True)
    ok = await hs.add_helper(_DB(), "رضا محمدی", "989120000001", sender_instance_id="S1",
                             require_full_name=True)
    assert ok.name == "رضا محمدی"


# ── full-name enforcement through the V29 API flag (V28 default stays lenient) ─
@pytest.mark.asyncio
async def test_api_full_name_flag_rejects_single_token(monkeypatch):
    import app.api.v1.warmup_helpers as api
    from fastapi import HTTPException
    # V39 PART 2 added an eligibility gate before add_helper; this test targets the full-name rule
    # (orthogonal), so no-op the gate (fully covered in test_v39_part2).
    async def _noop(*a, **k): return None
    monkeypatch.setattr("app.services.sender_eligibility.enforce_for_assignment", _noop)
    # V29 UI sends require_full_name=True → single token rejected
    with pytest.raises(HTTPException) as e:
        await api.create_helper(
            api.HelperBody(name="رضا", phone="989120000001", sender_instance_id="S1",
                           require_full_name=True), db=_DB())
    assert e.value.status_code == 400
    # V28 default (flag omitted) → single token still accepted
    out = await api.create_helper(
        api.HelperBody(name="رضا", phone="989120000001", sender_instance_id="S1"),
        db=_DB(results=[_Result(scalar=1), _Result(scalars=[])]))
    assert out["name"] == "رضا"
