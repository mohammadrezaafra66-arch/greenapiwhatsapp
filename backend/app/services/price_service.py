"""
Product price fetcher — reads directly from the Afrakala Supabase REST API.

Fetches active, in-stock products and (best-effort) joins them with the
`product_computed_prices_public` view to attach each product's `rounded_sale_price`.
Results are cached in Redis for PRICING_CACHE_MINUTES.

Normalized output: [{"name": "...", "price": <rounded_sale_price | None>}, ...]

Notes:
- Only anon-readable product columns are selected. `sku` and `category`
  are NOT granted to the anon role and would raise a 42501 permission error if
  requested, so they are intentionally omitted.
- The price join is best-effort: if the prices relation is missing or not
  readable by the anon role, products are still returned with price=None
  (downstream renders "تماس بگیرید" in that case).
"""
import json
import logging
import httpx
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger("afrakala.pricing")
redis_client = aioredis.from_url(settings.redis_url)

CACHE_KEY = "afrakala:products:cache"

# Columns the anon role is allowed to read on `products`.
_PRODUCT_SELECT = "id,name,model,capacity,brand_id"

# V15 — last outcome of the price-view fetch, so the UI can explain a missing price
# instead of silently rendering «تماس بگیرید» (which looks like an AI bug).
_LAST_PRICE_STATUS: dict = {"ok": None, "reason": "not fetched yet", "http": None, "count": 0}


def price_source_status() -> dict:
    """Diagnostic: the result of the most recent attempt to read the prices view."""
    return dict(_LAST_PRICE_STATUS)


def _headers() -> dict:
    return {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }


async def _fetch_price_map(client: httpx.AsyncClient) -> dict:
    """Return {product_id: rounded_sale_price} from the prices relation.

    Best-effort: returns an empty map if the relation is missing or not
    readable by the anon role, so product names still flow through.
    """
    try:
        resp = await client.get(
            f"{settings.supabase_url}/rest/v1/product_computed_prices_public",
            params={"select": "product_id,rounded_sale_price"},
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        # 401/403 with Postgres 42501 = the anon role lacks SELECT on the prices view.
        pg = ""
        try:
            pg = (e.response.json() or {}).get("code", "")
        except Exception:
            pass
        if code in (401, 403) or pg == "42501":
            reason = ("دسترسی anon به view «product_computed_prices_public» در Supabase وجود ندارد "
                      "(permission denied / 42501). برای نمایش قیمت، این دسترسی را در Supabase فعال کنید.")
        else:
            reason = f"prices view returned HTTP {code}"
        _LAST_PRICE_STATUS.update({"ok": False, "reason": reason, "http": code, "count": 0})
        logger.warning("PRICE FETCH FAILED — %s (HTTP %s, pg=%s)", reason, code, pg)
        return {}
    except Exception as e:
        _LAST_PRICE_STATUS.update({"ok": False, "reason": f"connection error: {e}", "http": None, "count": 0})
        logger.warning("PRICE FETCH FAILED (connection): %s", e)
        return {}
    price_map = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("product_id") is not None:
                price_map[str(row["product_id"])] = row.get("rounded_sale_price")
    non_null = sum(1 for v in price_map.values() if v)
    _LAST_PRICE_STATUS.update({
        "ok": non_null > 0,
        "reason": "ok" if non_null > 0 else "prices view readable but returned no non-zero prices",
        "http": 200, "count": non_null,
    })
    return price_map


async def _fetch_products(client: httpx.AsyncClient, category_filter: str | None = None) -> list[dict]:
    """Return active, in-stock products (anon-readable columns only).
    Optionally filter by category (best-effort — falls back to no filter on error)."""
    params = {
        "is_active": "eq.true",
        "stock_status": "neq.unavailable",
        "select": _PRODUCT_SELECT,
    }
    if category_filter:
        params["category"] = f"eq.{category_filter}"
    try:
        resp = await client.get(
            f"{settings.supabase_url}/rest/v1/products",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
    except Exception as e:
        if category_filter:
            print(f"[PriceService] category filter failed, retrying without it: {e}")
            return await _fetch_products(client, None)
        raise
    data = resp.json()
    return data if isinstance(data, list) else []


async def get_products(count: int = 3, category_filter: str | None = None) -> list[dict]:
    """Get up to N products with prices, joined from Supabase. Cached in Redis.
    Note: cache is bypassed when a category_filter is provided."""
    # Try cache first (only for the unfiltered case)
    if not category_filter:
        cached = await redis_client.get(CACHE_KEY)
        if cached:
            products = json.loads(cached)
            return products[:count]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            products_raw = await _fetch_products(client, category_filter)
            price_map = await _fetch_price_map(client)

        # Join products with their computed sale price. Keep every named
        # product; price may be None when the prices relation is unavailable.
        products = []
        for item in products_raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            price = price_map.get(str(item.get("id")))
            products.append({"name": name, "price": price})

        # Cache the unfiltered result for configured minutes
        if not category_filter:
            await redis_client.setex(
                CACHE_KEY,
                settings.pricing_cache_minutes * 60,
                json.dumps(products, ensure_ascii=False),
            )
        return products[:count]

    except Exception as e:
        print(f"[PriceService] Failed to fetch prices: {e}")
        return []


async def get_products_by_label(label_id: str, count: int = 3) -> list[dict]:
    """Get products that carry a specific product label (self-hosted Supabase)."""
    headers = _headers()
    try:
        # Get product_ids with this label
        links_url = f"{settings.supabase_url}/rest/v1/product_label_links?label_id=eq.{label_id}&select=product_id"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(links_url, headers=headers)
            if r.status_code != 200:
                return []
            links = r.json()

        if not links:
            return []

        product_ids = [str(l["product_id"]) for l in links if l.get("product_id") is not None]
        if not product_ids:
            return []
        ids_filter = "(" + ",".join(product_ids) + ")"

        products_url = f"{settings.supabase_url}/rest/v1/products?id=in.{ids_filter}&is_active=eq.true&select=id,name,model,capacity"
        prices_url = f"{settings.supabase_url}/rest/v1/product_computed_prices_public?product_id=in.{ids_filter}&select=product_id,rounded_sale_price"

        async with httpx.AsyncClient(timeout=10) as c:
            pr = await c.get(products_url, headers=headers)
            prr = await c.get(prices_url, headers=headers)

        products = pr.json() if pr.status_code == 200 else []
        prices = {
            str(p["product_id"]): p.get("rounded_sale_price")
            for p in (prr.json() if prr.status_code == 200 else [])
            if isinstance(p, dict) and p.get("product_id") is not None
        }

        result = []
        for p in products[:count]:
            result.append({"name": p.get("name", ""), "price": prices.get(str(p.get("id")))})
        return result
    except Exception as e:
        print(f"[PriceService] get_products_by_label failed: {e}")
        return []
