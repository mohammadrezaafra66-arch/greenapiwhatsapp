"""Redis-backed per-account rate limiting for high concurrency (A3).

Atomic Redis counters are the fast source of truth for send decisions at scale
(80+ accounts). This checks the HARD ceiling (daily + hourly); the per-account
warm-up cap and Meta limits (Account.computed_daily_limit) still apply on top.
Keys are Tehran-day/hour scoped and auto-expire, so no cleanup job is needed.
"""
import redis.asyncio as aioredis
from datetime import datetime
import pytz
from app.config import settings

TEHRAN_TZ = pytz.timezone("Asia/Tehran")
_redis = None


async def get_redis():
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _keys(account_id: str):
    now = datetime.now(TEHRAN_TZ)
    return f"sent:{account_id}:{now:%Y%m%d}", f"sent:{account_id}:{now:%Y%m%d%H}"


async def can_send(account_id: str, daily_limit: int, hourly_limit: int) -> tuple[bool, str]:
    """Return (allowed, reason). Uses atomic Redis counters, not DB reads."""
    r = await get_redis()
    day_key, hour_key = _keys(account_id)
    day_count = int(await r.get(day_key) or 0)
    hour_count = int(await r.get(hour_key) or 0)
    if daily_limit is not None and day_count >= daily_limit:
        return False, f"سقف روزانه ({daily_limit}) پر شده"
    if hourly_limit is not None and hour_count >= hourly_limit:
        return False, f"سقف ساعتی ({hourly_limit}) پر شده"
    return True, "ok"


async def record_send(account_id: str):
    """Atomically increment day + hour counters with TTLs."""
    r = await get_redis()
    day_key, hour_key = _keys(account_id)
    pipe = r.pipeline()
    pipe.incr(day_key)
    pipe.expire(day_key, 172800)  # 2 days
    pipe.incr(hour_key)
    pipe.expire(hour_key, 7200)   # 2 hours
    await pipe.execute()


async def get_counts(account_id: str) -> dict:
    r = await get_redis()
    day_key, hour_key = _keys(account_id)
    return {
        "sent_today": int(await r.get(day_key) or 0),
        "sent_this_hour": int(await r.get(hour_key) or 0),
    }
