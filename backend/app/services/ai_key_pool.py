"""V12 — manages a pool of AI API keys across providers with random working-key
selection. Failed/rate-limited keys are auto-skipped and auto-recover over time."""
import random
from datetime import datetime, timedelta
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models.ai_key import AIKey

RATE_LIMIT_COOLDOWN = timedelta(minutes=15)
RECHECK_STALE_AFTER = timedelta(minutes=15)


def select_key(keys, now: datetime):
    """Pure selection logic (unit-testable, no DB).
    Skip 'invalid' and currently rate-limited keys. Prefer 'working' keys;
    otherwise pick from any usable key. Random choice among the eligible pool."""
    usable = [
        k for k in keys
        if k.status != "invalid"
        and (k.rate_limited_until is None or k.rate_limited_until < now)
    ]
    if not usable:
        return None
    working = [k for k in usable if k.status == "working"]
    pool = working if working else usable
    return random.choice(pool)


async def pool_has_keys() -> bool:
    """True if there is at least one active key in the pool. When False, callers
    fall back to env-var keys so existing setups keep working."""
    async with AsyncSessionLocal() as db:
        n = await db.execute(
            select(func.count()).select_from(AIKey).where(AIKey.is_active == True)
        )
        return (n.scalar() or 0) > 0


async def get_working_key(provider: str | None = None) -> AIKey | None:
    """Return a random active, non-rate-limited, non-invalid key.
    If provider given, restrict to it; otherwise any provider. Prefers 'working'."""
    async with AsyncSessionLocal() as db:
        query = select(AIKey).where(AIKey.is_active == True)
        if provider:
            query = query.where(AIKey.provider == provider)
        result = await db.execute(query)
        keys = list(result.scalars().all())
    return select_key(keys, datetime.utcnow())


async def mark_success(key_id):
    async with AsyncSessionLocal() as db:
        k = await db.get(AIKey, key_id)
        if k:
            k.status = "working"
            k.success_count += 1
            k.last_checked_at = datetime.utcnow()
            k.last_error = None
            k.rate_limited_until = None
            await db.commit()


async def mark_failure(key_id, error: str, is_rate_limit: bool = False, is_invalid: bool = False):
    async with AsyncSessionLocal() as db:
        k = await db.get(AIKey, key_id)
        if k:
            k.fail_count += 1
            k.last_checked_at = datetime.utcnow()
            k.last_error = (error or "")[:500]
            if is_invalid:
                k.status = "invalid"
            elif is_rate_limit:
                k.status = "rate_limited"
                k.rate_limited_until = datetime.utcnow() + RATE_LIMIT_COOLDOWN
            else:
                k.status = "failed"
            await db.commit()


async def recheck_stale_keys() -> dict:
    """Re-test keys that are 'failed'/'rate_limited' and haven't been checked in
    >15 min, so they auto-recover once quota/rate-limit resets. Also revives keys
    whose rate-limit window has expired. Returns a small summary."""
    from app.services.gpt_service import _call_provider
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AIKey).where(AIKey.is_active == True))
        keys = list(result.scalars().all())

    summary = {"rechecked": 0, "recovered": 0, "still_bad": 0}
    for k in keys:
        stale = k.last_checked_at is None or (now - k.last_checked_at) > RECHECK_STALE_AFTER
        rl_expired = k.rate_limited_until is not None and k.rate_limited_until < now
        if k.status not in ("failed", "rate_limited"):
            continue
        if not (stale or rl_expired):
            continue
        summary["rechecked"] += 1
        try:
            await _call_provider(k.provider, k.api_key, "test", max_tokens=5)
            await mark_success(k.id)
            summary["recovered"] += 1
        except Exception as e:
            msg = str(e)
            is_rl = "429" in msg or "rate" in msg.lower() or "quota" in msg.lower()
            is_inv = "401" in msg or "invalid" in msg.lower() or "unauthorized" in msg.lower()
            await mark_failure(k.id, msg, is_rate_limit=is_rl, is_invalid=is_inv)
            summary["still_bad"] += 1
    return summary
