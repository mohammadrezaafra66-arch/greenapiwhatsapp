"""
Time-based rate limiter for message sending.
Controls how many messages can be sent per hour based on configured schedule.
"""
import redis.asyncio as aioredis
from datetime import datetime
import pytz
from app.config import settings

redis_client = aioredis.from_url(settings.redis_url)
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

# Default schedule — can be overridden via API
DEFAULT_SCHEDULE = [
    {"hour_start": 8,  "hour_end": 9,  "max_per_hour": 30},
    {"hour_start": 9,  "hour_end": 10, "max_per_hour": 70},
    {"hour_start": 10, "hour_end": 11, "max_per_hour": 200},
    {"hour_start": 11, "hour_end": 22, "max_per_hour": 500},
    # 22:00 - 08:00 → no sending (not in list = blocked)
]


def get_current_tehran_hour() -> int:
    return datetime.now(TEHRAN_TZ).hour


def get_max_per_hour_for_current_time() -> int:
    """Returns max messages allowed in current hour. 0 = sending blocked."""
    current_hour = get_current_tehran_hour()
    for slot in DEFAULT_SCHEDULE:
        if slot["hour_start"] <= current_hour < slot["hour_end"]:
            return slot["max_per_hour"]
    return 0  # Blocked (night time)


async def can_send_now(account_id: str) -> bool:
    """Check if account can send a message right now."""
    max_per_hour = get_max_per_hour_for_current_time()
    if max_per_hour == 0:
        return False

    # Check hourly window for this account
    hour_key = f"ratelimit:{account_id}:{get_current_tehran_hour()}"
    count = await redis_client.get(hour_key)
    if count and int(count) >= max_per_hour:
        return False
    return True


async def record_send(account_id: str):
    """Record a sent message for rate limiting."""
    hour_key = f"ratelimit:{account_id}:{get_current_tehran_hour()}"
    pipe = redis_client.pipeline()
    pipe.incr(hour_key)
    pipe.expire(hour_key, 3700)  # 1 hour + buffer
    await pipe.execute()


async def get_send_stats(account_id: str) -> dict:
    current_hour = get_current_tehran_hour()
    hour_key = f"ratelimit:{account_id}:{current_hour}"
    sent_this_hour = int(await redis_client.get(hour_key) or 0)
    max_this_hour = get_max_per_hour_for_current_time()
    return {
        "sent_this_hour": sent_this_hour,
        "max_this_hour": max_this_hour,
        "can_send": max_this_hour > 0 and sent_this_hour < max_this_hour,
        "tehran_hour": current_hour
    }
