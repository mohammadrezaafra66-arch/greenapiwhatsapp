"""V27 PART 5 — lazy, cached WhatsApp-existence validation.

Avoids CheckWhatsapp abuse: a number is checked at most once per NUMBER_CHECK_TTL_DAYS, the
result cached; already-validated numbers are never re-queried. Non-existent numbers are
excluded from sending with a logged reason. Everything is fail-open — a check error or a
client without check_whatsapp never blocks a legitimate send.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.number_check import WhatsappNumberCheck

logger = logging.getLogger("afrakala.number_validation")

NUMBER_CHECK_TTL_DAYS = 30
NONEXISTENT_REASON_FA = "این شماره در واتساپ وجود ندارد — از کمپین کنار گذاشته شد."


def cache_is_fresh(row, now: datetime | None = None,
                   ttl_days: int = NUMBER_CHECK_TTL_DAYS) -> bool:
    """True if a cached check row is recent enough to trust (no re-check needed)."""
    if row is None or getattr(row, "checked_at", None) is None:
        return False
    now = now or datetime.utcnow()
    return (now - row.checked_at) < timedelta(days=ttl_days)


async def _get_cached(db, phone: str):
    return (await db.execute(
        select(WhatsappNumberCheck).where(WhatsappNumberCheck.phone == str(phone))
    )).scalar_one_or_none()


async def validate_number(db, phone: str, client, now: datetime | None = None) -> dict:
    """Return {"exists": bool, "from_cache": bool, "checked": bool} for one number.

    Uses a fresh cached result when available (NO API call); otherwise does exactly ONE
    CheckWhatsapp, caches it, and returns it. Fail-open: any error → exists=True, not cached."""
    now = now or datetime.utcnow()
    row = await _get_cached(db, phone)
    if cache_is_fresh(row, now):
        return {"exists": bool(row.exists), "from_cache": True, "checked": False}
    try:
        exists = bool(await client.check_whatsapp(phone))
    except Exception as e:
        logger.info("check_whatsapp unavailable/failed for %s (%s) — fail-open", phone, e)
        return {"exists": True, "from_cache": False, "checked": False}
    reason = None if exists else NONEXISTENT_REASON_FA
    if row is None:
        db.add(WhatsappNumberCheck(phone=str(phone), exists=exists, reason=reason, checked_at=now))
    else:
        row.exists = exists
        row.reason = reason
        row.checked_at = now
    return {"exists": exists, "from_cache": False, "checked": True}


async def filter_numbers(db, phones: list[str], client, now: datetime | None = None) -> dict:
    """Split a list of numbers into {"valid": [...], "excluded": [{"phone","reason"}]}.
    Each number is validated lazily (cache-first, one check max per TTL)."""
    now = now or datetime.utcnow()
    valid, excluded = [], []
    for phone in phones:
        res = await validate_number(db, phone, client, now)
        if res["exists"]:
            valid.append(phone)
        else:
            excluded.append({"phone": phone, "reason": NONEXISTENT_REASON_FA})
            logger.info("excluded non-existent WhatsApp number from campaign: %s", phone)
    return {"valid": valid, "excluded": excluded}
