"""
Product price fetcher — reads directly from the Afrakala Supabase REST API.

Fetches active, in-stock products and joins them with the public
`product_computed_prices_public` view to attach each product's
`rounded_sale_price`. Results are cached in Redis for PRICING_CACHE_MINUTES.

Normalized output: [{"name": "...", "price": <rounded_sale_price | None>}, ...]

Note: only anon-readable product columns are selected. `sku` and `category`
are NOT granted to the anon role and would raise a 42501 permission error if
requested, so they are intentionally omitted.
"""
import json
import httpx
import redis.asyncio as aioredis
from app.config import settings

redis_client = aioredis.from_url(settings.redis_url)

CACHE_KEY = "afrakala:products:cache"

# Columns the anon role is allowed to read on `products`.
_PRODUCT_SELECT = "id,name,model,capacity,brand_id"


def _headers() -> dict:
    return {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }


async def _fetch_price_map(client: httpx.AsyncClient) -> dict:
    """Return {product_id: rounded_sale_price} from the public prices view."""
    resp = await client.get(
        f"{settings.supabase_url}/rest/v1/product_computed_prices_public",
        params={"select": "product_id,rounded_sale_price"},
        headers=_headers(),
    )
    resp.raise_for_status()
    rows = resp.json()
    price_map = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("product_id") is not None:
                price_map[str(row["product_id"])] = row.get("rounded_sale_price")
    return price_map


async def _fetch_products(client: httpx.AsyncClient) -> list[dict]:
    """Return active, in-stock products (anon-readable columns only)."""
    resp = await client.get(
        f"{settings.supabase_url}/rest/v1/products",
        params={
            "is_active": "eq.true",
            "stock_status": "neq.unavailable",
            "select": _PRODUCT_SELECT,
        },
        headers=_headers(),
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


async def get_products(count: int = 3) -> list[dict]:
    """Get up to N products with prices, joined from Supabase. Cached in Redis."""
    # Try cache first
    cached = await redis_client.get(CACHE_KEY)
    if cached:
        products = json.loads(cached)
        return products[:count]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            products_raw = await _fetch_products(client)
            price_map = await _fetch_price_map(client)

        # Join products with their computed sale price
        products = []
        for item in products_raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            products.append({
                "name": name,
                "price": price_map.get(str(item.get("id"))),
            })

        # Cache for configured minutes
        await redis_client.setex(
            CACHE_KEY,
            settings.pricing_cache_minutes * 60,
            json.dumps(products, ensure_ascii=False),
        )
        return products[:count]

    except Exception as e:
        print(f"[PriceService] Failed to fetch prices: {e}")
        return []
