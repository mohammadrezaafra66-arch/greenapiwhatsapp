"""V43 PART 1 (reconciled by V49 PART 2) — the reporting top-products endpoint honors every still-
valid date-range option (7/14/30/60/90) and CLAMPS any wider request to the real 90-day retention
ceiling, echoing the clamped `period_days` so the UI never implies more history than actually exists.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.api.v1 import reporting as ui
from app.services import product_reports as prs
from app.workers.tasks import PRODUCT_MENTION_RETENTION_DAYS

ALL_TIME_DAYS = 36500   # the old frontend "همه‌ی زمان‌ها" sentinel — now clamped, no longer selectable


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


# ── the still-valid options are honored verbatim ──────────────────────────────
@pytest.mark.parametrize("days", [7, 14, 30, 60, 90])
@pytest.mark.asyncio
async def test_valid_range_options_are_honored(days):
    db = _FakeDB(AGG)
    out = await ui.top_repeated_products(limit=150, days=days, db=db)
    assert out["period_days"] == days              # within the 90-day ceiling → passed through
    assert out["total_products"] == len(AGG)
    assert [p["product_name"] for p in out["products"]] == ["محصول الف", "محصول ب"]


# ── any window wider than 90 days is clamped down to exactly 90 ────────────────
@pytest.mark.parametrize("days", [91, 180, 365, ALL_TIME_DAYS])
@pytest.mark.asyncio
async def test_windows_wider_than_90_days_are_clamped(days):
    db = _FakeDB(AGG)
    out = await ui.top_repeated_products(limit=150, days=days, db=db)
    assert out["period_days"] == PRODUCT_MENTION_RETENTION_DAYS == 90
    assert out["total_products"] == len(AGG)


def test_ceiling_matches_the_retention_window():
    # The UI clamp and the purge window are the same 90 — they can never drift.
    assert PRODUCT_MENTION_RETENTION_DAYS == 90


@pytest.mark.asyncio
async def test_default_window_is_30_days():
    db = _FakeDB(AGG)
    out = await ui.top_repeated_products(db=db)   # default days=30
    assert out["period_days"] == 30
