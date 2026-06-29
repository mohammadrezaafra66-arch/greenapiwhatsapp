"""
Product price fetcher from internal Afrakala pricing API.
Caches results in Redis for PRICING_CACHE_MINUTES.
"""
import json
import httpx
import redis.asyncio as aioredis
from app.config import settings

redis_client = aioredis.from_url(settings.redis_url)

CACHE_KEY = "afrakala:products:cache"


async def get_products(count: int = 3) -> list[dict]:
    """Get top N products with prices from internal API."""
    # Try cache first
    cached = await redis_client.get(CACHE_KEY)
    if cached:
        products = json.loads(cached)
        return products[:count]

    # Fetch from API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(settings.pricing_api_url)
            resp.raise_for_status()
            data = resp.json()

        # Normalize the response (adapt based on actual API format)
        products = []
        if isinstance(data, list):
            for item in data:
                products.append({
                    "name": item.get("name") or item.get("product_name", ""),
                    "price": item.get("price") or item.get("sell_price", 0)
                })
        elif isinstance(data, dict):
            for name, price in data.items():
                products.append({"name": name, "price": price})

        # Cache for configured minutes
        await redis_client.setex(
            CACHE_KEY,
            settings.pricing_cache_minutes * 60,
            json.dumps(products)
        )
        return products[:count]

    except Exception as e:
        print(f"[PriceService] Failed to fetch prices: {e}")
        return []
