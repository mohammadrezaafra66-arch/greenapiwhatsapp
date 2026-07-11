"""V13.8 — drip sending: per-campaign daily send counter (Redis, keyed by Tehran date).

The key rolls over automatically at Tehran midnight (date in the key changes), so the
daily quota resets each day with no explicit reset needed."""
from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")
PAUSE_REASON = "سهمیه روزانه drip پر شد — فردا به‌طور خودکار ادامه می‌یابد"


def _today_key(campaign_id: str) -> str:
    d = datetime.now(TEHRAN).strftime("%Y%m%d")
    return f"drip:{campaign_id}:{d}"


async def drip_count_today(campaign_id: str) -> int:
    """How many messages this campaign has sent today (Tehran). 0 if Redis is down."""
    try:
        from app.services.redis_rate_limiter import get_redis
        r = await get_redis()
        return int(await r.get(_today_key(campaign_id)) or 0)
    except Exception:
        return 0


async def drip_incr(campaign_id: str) -> None:
    """Increment today's drip counter (2-day TTL). Non-fatal if Redis is down."""
    try:
        from app.services.redis_rate_limiter import get_redis
        r = await get_redis()
        key = _today_key(campaign_id)
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 172800)  # 2 days
        await pipe.execute()
    except Exception:
        pass
