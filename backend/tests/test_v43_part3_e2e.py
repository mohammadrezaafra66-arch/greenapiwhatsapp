"""V43 PART 3 (reconciled by V49 PART 2) — end-to-end: a date range clamped to the 90-day retention
ceiling + the max 1000-count limit + the V40 source filter/tagging all work together through the
existing top-products endpoint, with the clamped `days` threaded to the shared aggregation and each
source's tag preserved.
"""
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.api.v1 import reporting as ui
from app.services import product_reports as prs
from app.workers.tasks import PRODUCT_MENTION_RETENTION_DAYS

ALL_TIME_DAYS = 36500       # a wide legacy request; the endpoint clamps it to the 90-day ceiling
CAP = PRODUCT_MENTION_RETENTION_DAYS   # 90
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


@pytest.mark.parametrize("source", [None, "pv", "group", "status"])
@pytest.mark.asyncio
async def test_rolling_window_max_limit_with_each_source(source, monkeypatch):
    captured = {}
    real = prs.top_products_rows
    # V44 added `search`; V52 added `ai_merge`. The double must track the real signature or
    # every caller that passes a newer kwarg fails here with an unrelated TypeError.
    async def _spy(db, *, days, limit, source=None, search=None, ai_merge=False):
        captured.update(days=days, limit=limit, source=source)
        return await real(db, days=days, limit=limit, source=source, search=search,
                          ai_merge=ai_merge)
    monkeypatch.setattr(prs, "top_products_rows", _spy)

    rows = [_agg(f"محصول {i}") for i in range(MAX_LIMIT)]
    out = await ui.top_repeated_products(limit=MAX_LIMIT, days=ALL_TIME_DAYS, source=source,
                                         db=_FakeDB(rows))
    assert captured == {"days": CAP, "limit": MAX_LIMIT, "source": source}
    # and the endpoint echoes the clamped window + source and returns the full page.
    assert out["period_days"] == CAP == 90
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
    assert out["period_days"] == CAP
    p0, p1 = out["products"]
    # in_assistant tag flows from product_id (V40 behavior), unaffected by the wider limit/range.
    assert p0["in_assistant"] is False and p0["assistant_status"] == "خارج از دستیار"
    assert p1["in_assistant"] is True and p1["assistant_status"] == "در دستیار داریم"
