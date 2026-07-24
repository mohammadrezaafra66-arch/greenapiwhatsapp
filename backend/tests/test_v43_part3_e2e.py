"""V43 PART 3 — end-to-end: the largest date-range (all time) + the max 1000-count limit + the V40
source filter/tagging all work together through the existing top-products endpoint, with the exact
selected params threaded to the shared aggregation and each source's tag preserved.
"""
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.api.v1 import reporting as ui
from app.services import product_reports as prs

ALL_TIME_DAYS = 36500
MAX_LIMIT = 1000


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


def _agg(name, **kw):
    base = dict(product_name=name, product_id=None, mention_count=3, group_count=1,
                sender_count=2, last_mention=datetime(2026, 7, 22, 10, 0))
    base.update(kw)
    return SimpleNamespace(**base)


# ── all-time + 1000 + each source, together — params threaded, source echoed ─
@pytest.mark.parametrize("source", [None, "pv", "group", "status"])
@pytest.mark.asyncio
async def test_all_time_max_limit_with_each_source(source, monkeypatch):
    captured = {}
    real = prs.top_products_rows
    async def _spy(db, *, days, limit, source=None, search=None):   # V44 added `search`
        captured.update(days=days, limit=limit, source=source)
        return await real(db, days=days, limit=limit, source=source, search=search)
    monkeypatch.setattr(prs, "top_products_rows", _spy)

    rows = [_agg(f"محصول {i}") for i in range(MAX_LIMIT)]
    out = await ui.top_repeated_products(limit=MAX_LIMIT, days=ALL_TIME_DAYS, source=source,
                                         db=_FakeDB(rows))
    # the exact selected filters reached the shared aggregation together.
    assert captured == {"days": ALL_TIME_DAYS, "limit": MAX_LIMIT, "source": source}
    # and the endpoint echoes the window + source and returns the full page.
    assert out["period_days"] == ALL_TIME_DAYS
    assert out["source"] == source
    assert out["total_products"] == MAX_LIMIT
    assert out["products"][-1]["rank"] == MAX_LIMIT


# ── V40 source tagging preserved per row alongside the new options ────────────
@pytest.mark.asyncio
async def test_source_tags_preserved_with_new_options():
    rows = [
        _agg("محصول استوری", product_id=None),
        _agg("محصول گروه", product_id="CAT-1"),   # a catalog match → in_assistant tag
    ]
    out = await ui.top_repeated_products(limit=MAX_LIMIT, days=ALL_TIME_DAYS, source="status",
                                         db=_FakeDB(rows))
    p0, p1 = out["products"]
    # in_assistant tag flows from product_id (V40 behavior), unaffected by the wider limit/range.
    assert p0["in_assistant"] is False and p0["assistant_status"] == "خارج از دستیار"
    assert p1["in_assistant"] is True and p1["assistant_status"] == "در دستیار داریم"
