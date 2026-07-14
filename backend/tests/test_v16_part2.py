"""V16 PART 2 — catalog browse helpers (flatten / filter / paginate / brand names)."""
from app.services.catalog import flatten_catalog, filter_catalog, paginate, brand_names

CATALOG = [
    {"brand": "ال‌جی", "product_count": 2, "products": [
        {"id": "1", "name": "ساید الجی X24", "model": "X24", "price": 90000000, "price_formatted": "90,000,000"},
        {"id": "2", "name": "ساید الجی X39", "model": "X39", "price": None, "price_formatted": None},
    ]},
    {"brand": "بوش", "product_count": 1, "products": [
        {"id": "3", "name": "جاروبرقی بوش 8PRO5", "model": "8PRO5", "price": 30000000, "price_formatted": "30,000,000"},
    ]},
]


def test_flatten_sorts_cheapest_first_nulls_last():
    items = flatten_catalog(CATALOG)
    assert [it["id"] for it in items] == ["3", "1", "2"]   # 30M, 90M, then None
    assert items[0]["brand"] == "بوش"
    assert items[-1]["price"] is None


def test_flatten_empty_catalog():
    assert flatten_catalog([]) == []
    assert flatten_catalog(None) == []


def test_brand_names_distinct_sorted():
    assert brand_names(CATALOG) == sorted(["ال‌جی", "بوش"])
    assert brand_names([]) == []


def test_filter_by_brand():
    items = flatten_catalog(CATALOG)
    only_lg = filter_catalog(items, brands=["ال‌جی"])
    assert {it["brand"] for it in only_lg} == {"ال‌جی"}
    assert len(only_lg) == 2


def test_filter_by_search():
    items = flatten_catalog(CATALOG)
    hits = filter_catalog(items, search="8PRO5")
    assert len(hits) == 1 and hits[0]["id"] == "3"
    assert filter_catalog(items, search="ندارد") == []


def test_paginate_shape_and_slicing():
    items = flatten_catalog(CATALOG)
    p = paginate(items, skip=0, limit=2)
    assert p["total"] == 3 and p["skip"] == 0 and p["limit"] == 2
    assert len(p["items"]) == 2
    p2 = paginate(items, skip=2, limit=2)
    assert len(p2["items"]) == 1            # last page has the remainder
    assert p2["total"] == 3


def test_paginate_clamps_limit():
    p = paginate(flatten_catalog(CATALOG), skip=-5, limit=99999)
    assert p["skip"] == 0 and p["limit"] == 500
