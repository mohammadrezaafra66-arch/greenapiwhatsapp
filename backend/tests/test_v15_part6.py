"""V15 PART 6 — per-message real-time price fetch (Item 24)."""
import asyncio
from types import SimpleNamespace
from app.services import campaign_runner


def test_fetch_campaign_products_is_fresh_each_call(monkeypatch):
    """Two calls to the per-message fetch must reflect a price change between them
    (mock get_products returns price X, then price Y)."""
    calls = {"n": 0}

    async def fake_get_products(count):
        calls["n"] += 1
        price = 100 if calls["n"] == 1 else 200      # price changed between messages
        return [{"name": "کولر", "price": price}]

    monkeypatch.setattr(campaign_runner, "get_products", fake_get_products)
    campaign = SimpleNamespace(product_label_filter=None, product_count=3)

    first = asyncio.run(campaign_runner.fetch_campaign_products(campaign))
    second = asyncio.run(campaign_runner.fetch_campaign_products(campaign))

    assert first[0]["price"] == 100
    assert second[0]["price"] == 200                 # the SECOND message sees the NEW price
    assert calls["n"] == 2                            # fetched fresh both times (not reused)


def test_fetch_uses_label_filter_when_set(monkeypatch):
    seen = {}

    async def fake_by_label(label, count):
        seen["label"] = label
        return [{"name": "x", "price": 1}]

    monkeypatch.setattr(campaign_runner, "get_products_by_label", fake_by_label, raising=False)
    # patch the lazily-imported symbol too
    import app.services.price_service as ps
    monkeypatch.setattr(ps, "get_products_by_label", fake_by_label)

    campaign = SimpleNamespace(product_label_filter="lbl-1", product_count=3)
    out = asyncio.run(campaign_runner.fetch_campaign_products(campaign))
    assert seen["label"] == "lbl-1" and out[0]["price"] == 1
