"""V14 F23.6 — ban-prevention governors (Green API's documented numeric guidance,
encoded as HARD enforced limits). Pure functions so they are unit-testable and reused
by the campaign runner, the incident handler, and the protection UI.
"""
from datetime import datetime

# Green API documented guidance
DAILY_HARD_CAP = 200            # ≤ 200 messages/day/number
WARMUP_DAYS = 10               # first 10 days are the highest-risk period
WARMUP_NEW_CONTACTS_PER_DAY = 20
MIN_DELAY_FLOOR_MS = 500       # anything faster is flagged as automated
DEFAULT_DELAY_MS = 15000       # Green API's own safe recommendation
YELLOW_THROTTLE_FACTOR = 0.5


def in_cooldown(account, now: datetime | None = None) -> bool:
    """True while cooldown_until is in the future — the account is resting."""
    cd = getattr(account, "cooldown_until", None)
    if not cd:
        return False
    return (now or datetime.utcnow()) < cd


def is_throttled(account, now: datetime | None = None) -> bool:
    tu = getattr(account, "throttle_until", None)
    factor = getattr(account, "throttle_factor", 1.0) or 1.0
    if factor >= 1.0:
        return False
    if tu and (now or datetime.utcnow()) >= tu:
        return False   # throttle window elapsed
    return True


def effective_daily_cap(account, now: datetime | None = None) -> int:
    """The real per-day send ceiling: computed limit, hard-capped at 200, times the
    throttle factor while a throttle window is active."""
    base = min(int(account.computed_daily_limit or 0), DAILY_HARD_CAP)
    if is_throttled(account, now):
        factor = getattr(account, "throttle_factor", 1.0) or 1.0
        base = int(base * factor)
    return max(0, base)


def account_available(account, now: datetime | None = None) -> bool:
    """A campaign may use this account only if it's active AND not resting (cooldown)."""
    status = getattr(account, "status", None)
    status_val = getattr(status, "value", status)
    return status_val == "active" and not in_cooldown(account, now)


def clamp_delay_ms(ms) -> int:
    """Enforce the 500ms absolute floor between messages to different chats."""
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return DEFAULT_DELAY_MS
    return max(MIN_DELAY_FLOOR_MS, ms)


# ── warm-up new-contact cap (Redis daily counter) ───────────────────────────
def _new_contact_key(account_id: str, day: str) -> str:
    return f"newcontacts:{account_id}:{day}"


async def warmup_new_contact_allowed(account_id: str, days_active: int) -> bool:
    """During warm-up (< 10 days), allow at most 20 NEW contacts per day. Returns True
    if a new-contact send is allowed right now. Fail-open if Redis is unavailable."""
    if (days_active or 0) >= WARMUP_DAYS:
        return True
    try:
        from datetime import datetime as _dt
        import pytz
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        day = _dt.now(pytz.timezone("Asia/Tehran")).strftime("%Y%m%d")
        count = int(await r.get(_new_contact_key(account_id, day)) or 0)
        return count < WARMUP_NEW_CONTACTS_PER_DAY
    except Exception:
        return True


async def record_new_contact(account_id: str):
    try:
        from datetime import datetime as _dt
        import pytz
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        day = _dt.now(pytz.timezone("Asia/Tehran")).strftime("%Y%m%d")
        key = _new_contact_key(account_id, day)
        pipe = r.pipeline()
        pipe.incr(key); pipe.expire(key, 172800)
        await pipe.execute()
    except Exception:
        pass
