"""V28 PART 2 — sender selection + per-sender contact-list API.

Drives the endpoint functions directly with staged fake sessions. Proves:
  • listing a sender shows only that sender's own contacts (lists don't mix);
  • adding a contact without a name is rejected by the endpoint (HTTP 400);
  • exceeding the soft threshold returns the non-blocking banner but STILL saves (no block);
  • the senders endpoint lists every account (any can be a sender) with contact counts;
  • the sender role is reported independently of mesh warm-peer status.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from app.api.v1 import warmup_helpers as api
from app.models.warmup_helpers import WarmupHelper, WarmupHelperConfig


class _Scalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)
    def first(self): return self._items[0] if self._items else None


class _Result:
    def __init__(self, scalars=None, scalar=None, rows=None):
        self._scalars = list(scalars) if scalars is not None else []
        self._scalar = scalar
        self._rows = rows if rows is not None else None
    def scalars(self): return _Scalars(self._scalars)
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None
    def all(self): return list(self._rows) if self._rows is not None else list(self._scalars)


class _DB:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.commits = 0
    async def execute(self, *a, **k):
        return self._results.pop(0) if self._results else _Result()
    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def get(self, model, pk): return None


def _cfg(threshold=30, enabled=False):
    return WarmupHelperConfig(is_enabled=enabled, soft_warning_threshold=threshold)


# ── list scoped to a sender ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_shows_only_that_senders_contacts():
    rows = [WarmupHelper(name="رضا", phone="989120000001", sender_instance_id="S1"),
            WarmupHelper(name="مریم", phone="989120000002", sender_instance_id="S1")]
    db = _DB(results=[_Result(scalars=rows), _Result(scalars=[_cfg()])])
    out = await api.list_helpers(sender_instance_id="S1", db=db)
    assert out["sender_instance_id"] == "S1"
    assert out["count"] == 2
    assert all(h["sender_instance_id"] == "S1" for h in out["helpers"])
    assert out["soft_warning"] is None          # under threshold


# ── name mandatory at the endpoint ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_rejects_missing_name():
    db = _DB()
    with pytest.raises(HTTPException) as ei:
        await api.create_helper(api.HelperBody(name="  ", phone="989120000001",
                                               sender_instance_id="S1"), db=db)
    assert ei.value.status_code == 400


# ── soft threshold: banner but NOT blocked ───────────────────────────────────
@pytest.mark.asyncio
async def test_over_threshold_returns_banner_but_saves(monkeypatch):
    # V39 PART 2 added a sender-eligibility gate before add_helper; this test targets the soft
    # threshold banner (orthogonal), so no-op the gate (fully covered in test_v39_part2).
    async def _noop(*a, **k): return None
    monkeypatch.setattr("app.services.sender_eligibility.enforce_for_assignment", _noop)
    # add (no execute) → count_helpers_for_sender (scalar=31) → get_config (threshold 30)
    db = _DB(results=[_Result(scalar=31), _Result(scalars=[_cfg(threshold=30)])])
    out = await api.create_helper(api.HelperBody(name="نفر۳۱", phone="989120000031",
                                                 sender_instance_id="S1"), db=db)
    assert out["name"] == "نفر۳۱"                # saved (not blocked)
    assert out["soft_warning"] is not None       # banner present
    assert db.commits >= 1


@pytest.mark.asyncio
async def test_under_threshold_no_banner(monkeypatch):
    async def _noop(*a, **k): return None   # V39 PART 2 — no-op the eligibility gate (see above)
    monkeypatch.setattr("app.services.sender_eligibility.enforce_for_assignment", _noop)
    db = _DB(results=[_Result(scalar=5), _Result(scalars=[_cfg(threshold=30)])])
    out = await api.create_helper(api.HelperBody(name="نفر۵", phone="989120000005",
                                                 sender_instance_id="S1"), db=db)
    assert out["soft_warning"] is None


# ── senders list: any account, independent of warm-peer status ───────────────
@pytest.mark.asyncio
async def test_list_senders_includes_all_accounts_with_counts():
    accts = [
        SimpleNamespace(instance_id="A", name="acct-A", phone="9891", platform="whatsapp",
                        is_warm_peer=True, status=SimpleNamespace(value="active"),
                        created_at=datetime(2026, 1, 1)),
        SimpleNamespace(instance_id="B", name="acct-B", phone="9892", platform="telegram",
                        is_warm_peer=False, status=SimpleNamespace(value="active"),
                        created_at=datetime(2026, 1, 2)),
    ]
    # accounts query, then count group-by rows
    db = _DB(results=[_Result(scalars=accts), _Result(rows=[("A", 3), ("B", 0)])])
    out = await api.list_senders(db=db)
    by_id = {s["instance_id"]: s for s in out["senders"]}
    assert by_id["A"]["contact_count"] == 3 and by_id["A"]["is_warm_peer"] is True
    assert by_id["B"]["contact_count"] == 0 and by_id["B"]["is_warm_peer"] is False
    # a non-warm-peer account (B) is still a valid sender candidate
    assert by_id["B"]["platform"] == "telegram"


# ── threshold config endpoint ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_set_threshold_endpoint():
    db = _DB(results=[_Result(scalars=[_cfg(threshold=30)])])
    out = await api.set_threshold(api.ThresholdBody(threshold=45), db=db)
    assert out["soft_warning_threshold"] == 45
