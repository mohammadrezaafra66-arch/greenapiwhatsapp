"""V15 price diagnostic — a permission-denied prices view must be reported clearly."""
import asyncio
import httpx
from app.services import price_service


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.request = httpx.Request("GET", "http://x/rest/v1/product_computed_prices_public")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=self.request, response=httpx.Response(
                self.status_code, json=self._payload, request=self.request))


class _Client:
    def __init__(self, resp):
        self._resp = resp

    async def get(self, *a, **k):
        return self._resp


def test_permission_denied_view_is_reported():
    resp = _Resp(401, {"code": "42501", "message": "permission denied for view product_computed_prices_public"})
    asyncio.run(price_service._fetch_price_map(_Client(resp)))
    st = price_service.price_source_status()
    assert st["ok"] is False
    assert st["http"] == 401
    assert "product_computed_prices_public" in st["reason"]
    assert "Supabase" in st["reason"]


def test_readable_view_with_prices_is_ok():
    resp = _Resp(200, [{"product_id": "1", "rounded_sale_price": 76900000}])
    pm = asyncio.run(price_service._fetch_price_map(_Client(resp)))
    st = price_source_status = price_service.price_source_status()
    assert pm == {"1": 76900000}
    assert st["ok"] is True and st["count"] == 1


def test_readable_view_but_all_null_prices_flagged():
    resp = _Resp(200, [{"product_id": "1", "rounded_sale_price": None}])
    asyncio.run(price_service._fetch_price_map(_Client(resp)))
    st = price_service.price_source_status()
    assert st["ok"] is False
    assert "no non-zero prices" in st["reason"]
