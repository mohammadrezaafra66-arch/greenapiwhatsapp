"""V44 PART 3 — server-side search on the top-products report.

`search` filters the merged product rows by NORMALIZED name (same normalization as grouping), so a
search for one spelling matches every merged variant, works with the date-range/source filters, and
returns a clean empty list on no match.
"""
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.services import product_reports as prs

LAST = datetime(2026, 7, 23, 20, 0)


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _FakeDB:
    def __init__(self, agg_rows): self._agg = agg_rows; self.seen_source = "unset"
    async def execute(self, q):
        # record whether a source filter was compiled into the query (for the combined-filter test)
        self.seen_source = "source" in str(q).lower()
        return _FakeResult(self._agg)


def _agg(name, mention_count, *, sources="group", last_mention=LAST):
    return SimpleNamespace(product_name=name, product_id=None, mention_count=mention_count,
                           group_count=1, sender_count=1, sources=sources, last_mention=last_mention)


BATCH = [
    _agg("یخچال ساید بای ساید ال‌جی", 8),
    _agg("یخچال ساید بای ساید ال جی", 3),        # near-dup of the above → merges to 11
    _agg("مایکروویو سولاردام ال‌جی", 4),
    _agg("جاروبرقی بوش سری 8", 2),
    _agg("اسپرسوساز دلونگی", 5),
]


# ── a search returns only matching rows ──────────────────────────────────────
@pytest.mark.asyncio
async def test_search_filters_to_matching_products():
    out = await prs.top_products_rows(_FakeDB(BATCH), days=30, limit=150, search="یخچال")
    assert [r["product_name"] for r in out] == ["یخچال ساید بای ساید ال‌جی"]
    assert out[0]["mention_count"] == 11         # still the merged count


# ── search is tolerant of the same normalization as grouping ─────────────────
@pytest.mark.asyncio
async def test_search_matches_across_spelling_variants():
    # Searching the SPACE spelling «ال جی» must find the row (whose top spelling is the ZWNJ «ال‌جی»).
    out = await prs.top_products_rows(_FakeDB(BATCH), days=30, limit=150, search="ساید ال جی")
    assert len(out) == 1 and out[0]["product_name"] == "یخچال ساید بای ساید ال‌جی"
    # A Latin/Persian-digit-insensitive search finds «سری 8».
    out2 = await prs.top_products_rows(_FakeDB(BATCH), days=30, limit=150, search="سری ۸")
    assert [r["product_name"] for r in out2] == ["جاروبرقی بوش سری 8"]


# ── no match → clean empty list (not an error) ───────────────────────────────
@pytest.mark.asyncio
async def test_search_no_match_returns_empty():
    out = await prs.top_products_rows(_FakeDB(BATCH), days=30, limit=150, search="هدفون سونی")
    assert out == []


# ── empty / whitespace-only search behaves as no filter ──────────────────────
@pytest.mark.asyncio
async def test_blank_search_is_no_filter():
    out_none = await prs.top_products_rows(_FakeDB(BATCH), days=30, limit=150)
    out_blank = await prs.top_products_rows(_FakeDB(BATCH), days=30, limit=150, search="   ")
    assert len(out_none) == len(out_blank) == 4      # 5 raw rows → 4 merged products, unfiltered


# ── search composes with the source filter (both applied) ────────────────────
@pytest.mark.asyncio
async def test_search_with_source_filter_together():
    db = _FakeDB([_agg("اسپرسوساز دلونگی", 5, sources="status")])
    out = await prs.top_products_rows(db, days=30, limit=150, source="status", search="اسپرسو")
    assert db.seen_source is True                    # source filter reached the SQL
    assert len(out) == 1 and out[0]["product_name"] == "اسپرسوساز دلونگی"


# ── endpoint-level: search flows through top_repeated_products ────────────────
@pytest.mark.asyncio
async def test_endpoint_passes_search(monkeypatch):
    from app.api.v1 import reporting as ui
    async def _empty(*_a, **_k): return []
    monkeypatch.setattr("app.services.price_service.get_products", _empty)
    out = await ui.top_repeated_products(limit=150, days=30, search="یخچال", db=_FakeDB(BATCH))
    assert out["total_products"] == 1
    assert out["products"][0]["product_name"] == "یخچال ساید بای ساید ال‌جی"
