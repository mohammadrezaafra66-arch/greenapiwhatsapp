"""V28 PART 1 — generalize the helper schema (multi-sender, mandatory name, no hard cap).

Proves:
  • a contact saved with no name is rejected (mandatory-name safeguard survives);
  • a contact is scoped to its sender_instance_id;
  • NO hard cap blocks a large list (26th, 100th all allowed);
  • the soft-warning banner is informational (over threshold → text, under → None);
  • the soft-warning threshold config is retrievable/settable;
  • legacy (senderless) rows resolve to a main sender;
  • the OutreachBrief model persists a one-line brief tied to a sender.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.services import warmup_helper_service as hs
from app.models.warmup_helpers import WarmupHelper, WarmupHelperConfig, OutreachBrief


# ── staged-result fake session ───────────────────────────────────────────────
class _Scalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)
    def first(self): return self._items[0] if self._items else None


class _Result:
    def __init__(self, scalars=None, scalar=None):
        self._scalars = list(scalars) if scalars is not None else []
        self._scalar = scalar
    def scalars(self): return _Scalars(self._scalars)
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


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


# ── pure soft-warning ────────────────────────────────────────────────────────
def test_soft_warning_notice_threshold():
    assert hs.soft_warning_notice(31, 30) is not None
    assert hs.soft_warning_notice(30, 30) is None
    assert hs.soft_warning_notice(0, 30) is None
    # default threshold is 30
    assert hs.DEFAULT_SOFT_WARNING_THRESHOLD == 30
    assert hs.soft_warning_notice(31) is not None


# ── mandatory name ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_helper_rejects_empty_name():
    with pytest.raises(ValueError):
        await hs.add_helper(_DB(), "   ", "989120000001", sender_instance_id="S1")
    with pytest.raises(ValueError):
        await hs.add_helper(_DB(), None, "989120000001", sender_instance_id="S1")


@pytest.mark.asyncio
async def test_add_helper_requires_valid_phone():
    with pytest.raises(ValueError):
        await hs.add_helper(_DB(), "رضا", "---", sender_instance_id="S1")


# ── sender scoping ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_helper_sets_sender_instance_id():
    db = _DB()
    h = await hs.add_helper(db, "رضا", "+98 912 000 0001", sender_instance_id="SENDER-A")
    assert h.sender_instance_id == "SENDER-A"
    assert h.name == "رضا" and h.phone == "989120000001"
    assert h.is_active is True


# ── no hard cap ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_hard_cap_allows_large_list():
    # add_helper no longer consults any count — adding the 26th..100th just works
    for i in range(100):
        db = _DB()
        h = await hs.add_helper(db, f"c{i}", f"98912000{i:04d}", sender_instance_id="S1")
        assert h.is_active is True


# ── config threshold ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_soft_warning_threshold_default():
    cfg = WarmupHelperConfig(is_enabled=False, soft_warning_threshold=30)
    db = _DB(results=[_Result(scalars=[cfg])])
    assert await hs.get_soft_warning_threshold(db) == 30


@pytest.mark.asyncio
async def test_set_soft_warning_threshold():
    cfg = WarmupHelperConfig(is_enabled=False, soft_warning_threshold=30)
    db = _DB(results=[_Result(scalars=[cfg])])
    out = await hs.set_soft_warning_threshold(db, 50)
    assert out.soft_warning_threshold == 50 and db.commits >= 1


# ── count/list scoped to a sender ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_count_helpers_for_sender():
    db = _DB(results=[_Result(scalar=32)])
    assert await hs.count_helpers_for_sender(db, "S1") == 32


@pytest.mark.asyncio
async def test_list_helpers_for_sender_returns_only_that_sender():
    rows = [WarmupHelper(name="a", phone="9891", sender_instance_id="S1")]
    db = _DB(results=[_Result(scalars=rows)])
    out = await hs.list_helpers_for_sender(db, "S1")
    assert len(out) == 1 and out[0].sender_instance_id == "S1"


# ── legacy backfill: resolve a main sender ───────────────────────────────────
@pytest.mark.asyncio
async def test_resolve_main_sender_prefers_default_then_peer_then_first():
    a_default = SimpleNamespace(instance_id="DEF", is_default=True, is_warm_peer=False,
                                created_at=datetime(2026, 1, 2))
    a_peer = SimpleNamespace(instance_id="PEER", is_default=False, is_warm_peer=True,
                             created_at=datetime(2026, 1, 1))
    db = _DB(results=[_Result(scalars=[a_peer, a_default])])
    assert await hs.resolve_main_sender_instance_id(db) == "DEF"   # default wins

    db2 = _DB(results=[_Result(scalars=[a_peer])])
    assert await hs.resolve_main_sender_instance_id(db2) == "PEER"  # then warm peer

    a_plain = SimpleNamespace(instance_id="P1", is_default=False, is_warm_peer=False,
                              created_at=datetime(2026, 1, 5))
    db3 = _DB(results=[_Result(scalars=[a_plain])])
    assert await hs.resolve_main_sender_instance_id(db3) == "P1"    # else first active


# ── OutreachBrief model ──────────────────────────────────────────────────────
def test_outreach_brief_model():
    b = OutreachBrief(sender_instance_id="S1", brief_text="به شماره‌های جدید ما سلام بده")
    assert b.sender_instance_id == "S1"
    assert "سلام" in b.brief_text
