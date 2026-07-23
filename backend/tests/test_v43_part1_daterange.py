"""V43 PART 1 — the reporting top-products endpoint honors every new date-range option, including
the largest ("all time") window, using the EXISTING `days` query param with no code change to the
days handling (its cutoff has no upper clamp). Confirms defaults/behavior for existing windows are
unchanged and large windows do not error.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.api.v1 import reporting as ui
from app.services import product_reports as prs

ALL_TIME_DAYS = 36500   # matches the frontend "همه‌ی زمان‌ها" sentinel


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
    """Records the grouped top-products query and returns seeded aggregate rows."""
    def __init__(self, agg_rows): self._agg = agg_rows; self.queries = []
    async def execute(self, q):
        self.queries.append(str(q))
        return _FakeResult(self._agg)


def _agg(name, **kw):
    base = dict(product_name=name, product_id=None, mention_count=5, group_count=2,
                sender_count=3, last_mention=datetime(2026, 7, 20, 9, 0))
    base.update(kw)
    return SimpleNamespace(**base)


AGG = [_agg("محصول الف", mention_count=9), _agg("محصول ب", mention_count=4)]


# ── days passthrough for every new option (no upper clamp) ────────────────────
@pytest.mark.parametrize("days", [7, 14, 30, 60, 90, 180, 365, ALL_TIME_DAYS])
@pytest.mark.asyncio
async def test_top_products_accepts_every_range_option(days):
    db = _FakeDB(AGG)
    out = await ui.top_repeated_products(limit=150, days=days, db=db)
    assert out["period_days"] == days              # the exact selected window is honored
    assert out["total_products"] == len(AGG)
    assert [p["product_name"] for p in out["products"]] == ["محصول الف", "محصول ب"]


# ── the all-time window computes a valid, ~100-years-ago cutoff (no error) ─────
def test_all_time_cutoff_is_far_past_and_valid():
    cutoff = prs._cutoff(ALL_TIME_DAYS)
    assert isinstance(cutoff, datetime)
    # ~100 years back from now (well past any real mention), and strictly before a 1-year window.
    assert cutoff < datetime.utcnow() - timedelta(days=36000)
    assert prs._cutoff(ALL_TIME_DAYS) < prs._cutoff(365)


# ── existing default window (30) is unchanged ─────────────────────────────────
@pytest.mark.asyncio
async def test_default_window_unchanged():
    db = _FakeDB(AGG)
    out = await ui.top_repeated_products(db=db)   # defaults: days=30, limit=150
    assert out["period_days"] == 30
