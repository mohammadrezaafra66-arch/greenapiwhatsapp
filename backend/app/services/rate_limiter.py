import redis.asyncio as aioredis
from datetime import datetime
import pytz
from app.config import settings

redis_client = aioredis.from_url(settings.redis_url)
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

DEFAULT_SCHEDULE = [
    {"hour_start": 8,  "hour_end": 9,  "max_per_hour": 30},
    {"hour_start": 9,  "hour_end": 10, "max_per_hour": 70},
    {"hour_start": 10, "hour_end": 11, "max_per_hour": 200},
    {"hour_start": 11, "hour_end": 22, "max_per_hour": 500},
]

def get_tehran_hour() -> int:
    return datetime.now(TEHRAN_TZ).hour

def get_max_per_hour() -> int:
    h = get_tehran_hour()
    for slot in DEFAULT_SCHEDULE:
        if slot["hour_start"] <= h < slot["hour_end"]:
            return slot["max_per_hour"]
    return 0

async def can_send(account_id: str) -> bool:
    max_h = get_max_per_hour()
    if max_h == 0:
        return False
    h = get_tehran_hour()
    count = await redis_client.get(f"rate:{account_id}:{h}")
    return not count or int(count) < max_h

async def record_send(account_id: str):
    h = get_tehran_hour()
    key = f"rate:{account_id}:{h}"
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 3700)
    await pipe.execute()

async def get_stats(account_id: str) -> dict:
    h = get_tehran_hour()
    sent = int(await redis_client.get(f"rate:{account_id}:{h}") or 0)
    max_h = get_max_per_hour()
    return {"sent_this_hour": sent, "max_this_hour": max_h, "can_send": max_h > 0 and sent < max_h, "tehran_hour": h}


# ── Backward-compatible aliases (v1 names) ──────────────
get_current_tehran_hour = get_tehran_hour
get_max_per_hour_for_current_time = get_max_per_hour
can_send_now = can_send
get_send_stats = get_stats
