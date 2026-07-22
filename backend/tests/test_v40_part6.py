"""V40 PART 6 — per-contact advertising trend over time (unified across pv/group/status).

Proves: one contact's mentions — regardless of stored phone format across sources — collapse to the
same contact via the national 10-digit core; the timeline is chronological (newest first) with source
+ in_assistant; the per-product summary counts repeats correctly and flags in-assistant products.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.product_reports import phone_core, contact_trend_rows


def test_phone_core_matches_all_forms():
    core = "9121112233"
    assert phone_core("09121112233") == core
    assert phone_core("989121112233") == core
    assert phone_core("989121112233@c.us") == core
    assert phone_core("۰۹۱۲۱۱۱۲۲۳۳") == core        # Persian digits


class _Result:
    def __init__(self, rows): self._rows = rows
    def scalars(self): return self
    def all(self): return list(self._rows)


class _DB:
    def __init__(self, rows): self._rows = rows
    async def execute(self, q): return _Result(self._rows)


def _m(product, source, day, pid=None, phone="989121112233"):
    return SimpleNamespace(product_name=product, product_id=pid, source=source,
                           sender_phone=phone, group_name="بازار", mentioned_at=datetime(2026, 7, day, 9, 0))


@pytest.mark.asyncio
async def test_trend_timeline_and_summary():
    # Same contact across pv/group/status with DIFFERENT stored phone formats.
    rows = [
        _m("کولر گازی گری 18000", "status", 22, pid="cat-1", phone="989121112233@c.us"),
        _m("کولر گازی گری 18000", "group", 20, pid="cat-1", phone="09121112233"),
        _m("کولر گازی گری 18000", "pv", 18, pid="cat-1", phone="989121112233"),
        _m("یخچال سامسونگ", "group", 15, pid=None, phone="989121112233"),
    ]
    # rows come back newest-first from the query (order_by desc); the service preserves that.
    db = _DB(rows)
    out = await contact_trend_rows(db, phone="0912 111 2233", days=90)

    assert len(out["timeline"]) == 4
    assert out["timeline"][0]["source"] == "status"          # newest first
    assert out["timeline"][0]["in_assistant"] is True

    summary = {s["product_name"]: s for s in out["summary"]}
    assert summary["کولر گازی گری 18000"]["count"] == 3       # 5-times-style repeat count
    assert summary["کولر گازی گری 18000"]["in_assistant"] is True
    assert sorted(summary["کولر گازی گری 18000"]["sources"]) == ["group", "pv", "status"]
    assert summary["یخچال سامسونگ"]["count"] == 1
    assert summary["یخچال سامسونگ"]["in_assistant"] is False
    # summary is ordered by repeat count desc
    assert out["summary"][0]["product_name"] == "کولر گازی گری 18000"


@pytest.mark.asyncio
async def test_trend_empty_for_blank_phone():
    out = await contact_trend_rows(_DB([]), phone="", days=90)
    assert out == {"timeline": [], "summary": []}


@pytest.mark.asyncio
async def test_endpoint_shapes_shamsi_and_status(monkeypatch):
    from app.api.v1 import reporting as ui
    db = _DB([_m("کولر گازی گری 18000", "status", 22, pid="cat-1")])
    out = await ui.contact_trend(phone="09121112233", days=90, limit=500, db=db)
    assert out["total_mentions"] == 1
    assert out["timeline"][0]["assistant_status"] == "در دستیار داریم"
    assert out["timeline"][0]["time_shamsi"]
    assert out["summary"][0]["count"] == 1
