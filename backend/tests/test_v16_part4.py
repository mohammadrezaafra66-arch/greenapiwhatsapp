"""V16 PART 4 — live per-message pricing: short cache TTL + mid-campaign price change."""
import asyncio
import json
import pytest
from app.services import price_service


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.setex_ttls = []

    async def get(self, k):
        return self.store.get(k)

    async def setex(self, k, ttl, v):
        self.setex_ttls.append(ttl)
        self.store[k] = v

    async def delete(self, k):
        self.store.pop(k, None)


class _Resp:
    def __init__(self, payload):
        self.status_code = 200
        self._p = payload

    def json(self):
        return self._p

    def raise_for_status(self):
        pass


class _FakeClient:
    """Routes /products and /product_computed_prices_public; price is read live from `box`."""
    def __init__(self, box):
        self._box = box

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        if "product_computed_prices_public" in url:
            return _Resp([{"product_id": "p1", "rounded_sale_price": self._box["price"]}])
        if "/rest/v1/" in url:  # products
            return _Resp([{"id": "p1", "name": "کولر"}])
        return _Resp([])


def _patch(monkeypatch, redis, box):
    monkeypatch.setattr(price_service, "redis_client", redis)
    monkeypatch.setattr(price_service.httpx, "AsyncClient", lambda *a, **k: _FakeClient(box))


def test_cache_ttl_is_at_most_60s(monkeypatch):
    redis = _FakeRedis()
    box = {"price": 100}
    _patch(monkeypatch, redis, box)
    asyncio.run(price_service.get_products(1))
    assert redis.setex_ttls, "expected the result to be cached"
    assert all(ttl <= 60 for ttl in redis.setex_ttls)   # ≤60s freshness


def test_price_change_reflected_after_cache_cycle(monkeypatch):
    redis = _FakeRedis()
    box = {"price": 100}
    _patch(monkeypatch, redis, box)

    first = asyncio.run(price_service.get_products(1))
    assert first[0]["price"] == 100

    # price changes mid-campaign
    box["price"] = 200
    # within the TTL window the cached value is still served...
    cached = asyncio.run(price_service.get_products(1))
    assert cached[0]["price"] == 100

    # ...after the short TTL expires (simulated by the key dropping), the NEW price shows.
    asyncio.run(redis.delete(price_service.CACHE_KEY))
    fresh = asyncio.run(price_service.get_products(1))
    assert fresh[0]["price"] == 200                     # later message → new price


def test_config_default_ttl_le_60():
    from app.config import settings
    assert settings.price_cache_seconds <= 60
