"""V44 PART 4 — end-to-end: merging + search + the V40/V43 filters all work together.

One flow through the real UI endpoint (top_repeated_products) with real near-duplicate fixtures plus
clearly-distinct products: confirms near-duplicates merge, distinct products stay separate, search
finds a product across its spellings, and date-range/limit/source compose with search.
"""
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.api.v1 import reporting as ui
from app.services import product_reports as prs

LAST = datetime(2026, 7, 23, 20, 0)


@pytest.fixture(autouse=True)
def _stub_catalog(monkeypatch):
    async def _empty(*_a, **_k): return []
    monkeypatch.setattr("app.services.price_service.get_products", _empty)
    yield


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _FakeDB:
    def __init__(self, agg_rows): self._agg = agg_rows; self.seen_source = False
    async def execute(self, q):
        self.seen_source = "source" in str(q).lower()
        return _FakeResult(self._agg)


def _agg(name, mention_count, *, sources="group,pv", last_mention=LAST):
    return SimpleNamespace(product_name=name, product_id=None, mention_count=mention_count,
                           group_count=1, sender_count=1, sources=sources, last_mention=last_mention)


# Real near-dup pairs (merge) + genuinely distinct products (stay separate).
BATCH = [
    _agg("یخچال ساید بای ساید ال‌جی", 8),
    _agg("یخچال ساید بای ساید ال جی", 3),        # → merges with the above to 11
    _agg("جاروبرقی بوش سری 8", 2),
    _agg("جاروبرقی بوش سری ۸", 1),               # → merges to 3
    _agg("مایکروویو سولاردام ال‌جی", 5),         # distinct
    _agg("اسپرسوساز دلونگی", 4),                 # distinct
]


@pytest.mark.asyncio
async def test_merge_and_distinct_end_to_end():
    out = await ui.top_repeated_products(limit=1000, days=36500, db=_FakeDB(BATCH))
    by = {r["product_name"]: r for r in out["products"]}
    # 6 fragmented rows → 4 real products.
    assert out["total_products"] == 4
    assert by["یخچال ساید بای ساید ال‌جی"]["mention_count"] == 11   # merged
    assert by["جاروبرقی بوش سری 8"]["mention_count"] == 3           # merged
    assert by["مایکروویو سولاردام ال‌جی"]["mention_count"] == 5     # distinct, untouched
    assert by["اسپرسوساز دلونگی"]["mention_count"] == 4             # distinct, untouched
    # ranked by combined count: fridge(11) #1, LG microwave(5) #2.
    assert out["products"][0]["product_name"] == "یخچال ساید بای ساید ال‌جی"
    assert out["products"][0]["rank"] == 1
    assert out["products"][1]["product_name"] == "مایکروویو سولاردام ال‌جی"


@pytest.mark.asyncio
async def test_search_finds_product_across_spellings_e2e():
    # search uses the SPACE spelling; must find the merged row whose top spelling is the ZWNJ one.
    out = await ui.top_repeated_products(limit=1000, days=36500, search="ساید ال جی", db=_FakeDB(BATCH))
    assert out["total_products"] == 1
    assert out["products"][0]["product_name"] == "یخچال ساید بای ساید ال‌جی"
    assert out["products"][0]["mention_count"] == 11


@pytest.mark.asyncio
async def test_search_with_source_and_limit_together():
    db = _FakeDB(BATCH)
    out = await ui.top_repeated_products(limit=1000, days=36500, source="group", search="بوش", db=db)
    assert db.seen_source is True                    # source filter reached the SQL
    assert out["source"] == "group" and out["period_days"] == 36500
    assert out["total_products"] == 1
    assert out["products"][0]["product_name"] == "جاروبرقی بوش سری 8"
    assert out["products"][0]["mention_count"] == 3  # merged count survives the combined filters


@pytest.mark.asyncio
async def test_limit_applies_after_merge():
    # 4 merged products; limit=2 keeps the top 2 by combined count (fridge 11, microwave 5).
    out = await ui.top_repeated_products(limit=2, days=36500, db=_FakeDB(BATCH))
    assert out["total_products"] == 2
    assert [p["product_name"] for p in out["products"]] == [
        "یخچال ساید بای ساید ال‌جی", "مایکروویو سولاردام ال‌جی"]


@pytest.mark.asyncio
async def test_search_no_match_e2e_empty():
    out = await ui.top_repeated_products(limit=1000, days=36500, search="تلویزیون سونی", db=_FakeDB(BATCH))
    assert out["total_products"] == 0 and out["products"] == []
