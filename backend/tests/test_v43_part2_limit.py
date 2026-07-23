"""V43 PART 2 — the top-products path honors a `limit` as high as 1000 (raised clamp ceiling),
while the default clamp ceiling for every OTHER caller is unchanged. Existing lower limits behave
exactly as before.
"""
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.api.v1 import reporting as ui
from app.services import product_reports as prs


@pytest.fixture(autouse=True)
def _stub_catalog(monkeypatch):
    async def _empty(*_a, **_k):
        return []
    monkeypatch.setattr("app.services.price_service.get_products", _empty)
    yield


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _FakeDB:
    def __init__(self, agg_rows): self._agg = agg_rows
    async def execute(self, q): return _FakeResult(self._agg)


def _agg(name):
    return SimpleNamespace(product_name=name, product_id=None, mention_count=1, group_count=1,
                           sender_count=1, last_mention=datetime(2026, 7, 20, 9, 0))


# ── the top-products aggregation raises its ceiling to 1000 ───────────────────
@pytest.mark.asyncio
async def test_top_products_rows_uses_1000_ceiling(monkeypatch):
    seen = {}
    real = prs.clamp_limit
    def _spy(limit, hi=500):
        seen["hi"] = hi
        return real(limit, hi)
    monkeypatch.setattr(prs, "clamp_limit", _spy)
    await prs.top_products_rows(_FakeDB([]), days=30, limit=1000)
    assert seen["hi"] == 1000                       # this path now clamps at 1000, not 500


# ── clamp_limit itself: 1000 honored with hi=1000; DEFAULT ceiling unchanged (500) ──
def test_clamp_limit_ceilings():
    assert prs.clamp_limit(1000, hi=1000) == 1000
    assert prs.clamp_limit(5000, hi=1000) == 1000   # above max → capped at 1000
    assert prs.clamp_limit(150) == 150              # normal value untouched
    assert prs.clamp_limit(1000) == 500             # DEFAULT ceiling unchanged for other callers
    assert prs.clamp_limit(0) == 1                  # floor unchanged


# ── endpoint returns up to `limit` rows at the max of 1000 without error ──────
@pytest.mark.asyncio
async def test_endpoint_handles_limit_1000():
    rows = [_agg(f"محصول {i}") for i in range(1000)]
    out = await ui.top_repeated_products(limit=1000, days=36500, db=_FakeDB(rows))
    assert out["total_products"] == 1000
    assert out["products"][0]["rank"] == 1 and out["products"][-1]["rank"] == 1000


# ── existing lower-limit behavior is unchanged ───────────────────────────────
@pytest.mark.asyncio
async def test_existing_limits_unchanged():
    rows = [_agg(f"محصول {i}") for i in range(5)]
    out = await ui.top_repeated_products(limit=150, days=30, db=_FakeDB(rows))
    assert out["total_products"] == 5               # fewer than limit → returns what exists
