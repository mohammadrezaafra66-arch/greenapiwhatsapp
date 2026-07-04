import redis.asyncio as aioredis
from datetime import datetime, timedelta
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

def _global_max_at_hour(hour: int) -> int:
    for slot in DEFAULT_SCHEDULE:
        if slot["hour_start"] <= hour < slot["hour_end"]:
            return slot["max_per_hour"]
    return 0

def seconds_until_send_window() -> int:
    """Seconds until the daily send window opens (08:00 Tehran).
    Returns 0 if the window is currently open."""
    if get_max_per_hour() > 0:
        return 0
    now = datetime.now(TEHRAN_TZ)
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now.hour >= 8:
        # Past today's window (>=22) → next open is tomorrow 08:00
        target = target + timedelta(days=1)
    return max(1, int((target - now).total_seconds()))

async def seconds_until_account_window(account_id: str) -> int:
    """Seconds until THIS account's send window next opens, honoring its
    per-account hour schedule (falling back to the global schedule per hour).
    Returns 0 if the account can send in the current hour."""
    from app.database import AsyncSessionLocal
    from app.models.account_hour_schedule import AccountHourSchedule
    from sqlalchemy import select
    import uuid as _uuid

    now = datetime.now(TEHRAN_TZ)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(AccountHourSchedule).where(
                AccountHourSchedule.account_id == _uuid.UUID(account_id),
                AccountHourSchedule.is_active == True,
            )
        )).scalars().all()

    def max_at(hour: int) -> int:
        # A matching per-account slot wins (even if 0 = intentionally blocked);
        # otherwise fall back to the global schedule for that hour.
        for r in rows:
            if r.hour_start <= hour < r.hour_end:
                return r.max_per_hour
        return _global_max_at_hour(hour)

    if max_at(now.hour) > 0:
        return 0
    for offset in range(1, 25):
        hour = (now.hour + offset) % 24
        if max_at(hour) > 0:
            target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=offset)
            return max(1, int((target - now).total_seconds()))
    return 3600  # no open hour found in the next 24h — retry in an hour

async def get_max_per_hour_for_account(account_id: str) -> int:
    """
    Returns max messages/hour for a specific account at current Tehran hour.
    Checks account_hour_schedules first; falls back to DEFAULT_SCHEDULE.
    Returns 0 if sending is blocked.
    """
    from app.database import AsyncSessionLocal
    from app.models.account_hour_schedule import AccountHourSchedule
    from sqlalchemy import select
    import uuid as _uuid

    h = get_tehran_hour()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AccountHourSchedule).where(
                AccountHourSchedule.account_id == _uuid.UUID(account_id),
                AccountHourSchedule.is_active == True,
                AccountHourSchedule.hour_start <= h,
                AccountHourSchedule.hour_end > h,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row.max_per_hour
    # fallback to global
    return get_max_per_hour()


async def get_hour_prompt_for_account(account_id: str) -> tuple[str | None, str | None, bool]:
    """Returns (gpt_prompt, message_template, include_products) for account at current
    hour, or (None, None, False) when no active slot matches."""
    from app.database import AsyncSessionLocal
    from app.models.account_hour_schedule import AccountHourSchedule
    from sqlalchemy import select
    import uuid as _uuid
    h = get_tehran_hour()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AccountHourSchedule).where(
                AccountHourSchedule.account_id == _uuid.UUID(account_id),
                AccountHourSchedule.is_active == True,
                AccountHourSchedule.hour_start <= h,
                AccountHourSchedule.hour_end > h,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row.gpt_prompt, row.message_template, bool(row.include_products)
    return None, None, False


async def can_send(account_id: str) -> bool:
    max_h = await get_max_per_hour_for_account(account_id)
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
