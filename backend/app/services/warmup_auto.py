"""V15 Item 26 — managed auto warm-up for new accounts.

A new number needs ~10 days of gentle activity before bulk sending, or WhatsApp cards it.
When `auto_warmup` is on, the account:
  - Day 1–3:  only RECEIVES (no proactive sends).
  - Day 4–7:  sends ≤ 3/day, reply-only (to contacts who messaged us first — the safest sends).
  - Day 8–10: sends ≤ 10/day, still reply-first.
  - Day 11+:  warmup_completed=True → available for campaigns.
Accounts in active warm-up are EXCLUDED from campaign account selection (like cooldown).
Pure helpers below are unit-testable; the daily beat task drives the sends.
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient

logger = logging.getLogger("afrakala.warmup")

WARMUP_TOTAL_DAYS = 10

# Friendly, low-risk reply templates used during warm-up.
WARMUP_TEMPLATES = [
    "سلام، ممنون از پیامتان. در خدمتیم. 🌟",
    "با تشکر از پیام شما، بله در خدمتیم.",
    "سلام و درود، پیام شما دریافت شد. خوشحال می‌شویم کمکتان کنیم.",
    "ممنون از تماس شما. در اسرع وقت پاسخگو هستیم.",
]


def warmup_day(account, now: datetime | None = None) -> int:
    """1-based day number since warm-up started (day 1 = the first 24h). 0 if not started."""
    started = getattr(account, "warmup_started_at", None)
    if not started:
        return 0
    now = now or datetime.utcnow()
    return max(1, (now - started).days + 1)


def warmup_daily_limit(day: int) -> int:
    """Proactive-send cap for a given warm-up day."""
    if day <= 0:
        return 0
    if day <= 3:
        return 0          # receive-only
    if day <= 7:
        return 3
    if day <= WARMUP_TOTAL_DAYS:
        return 10
    return 0              # completed — governed normally, not here


def in_active_warmup(account) -> bool:
    """True while an account is being auto-warmed → keep it out of bulk campaigns."""
    return bool(getattr(account, "auto_warmup", False)) and not getattr(account, "warmup_completed", False)


async def _recent_inbound_phones(instance_id: str, db, limit: int) -> list[str]:
    """Distinct phones that messaged this account in the last 3 days (reply-first targets)."""
    from app.models.inbox import InboxMessage
    cutoff = datetime.utcnow() - timedelta(days=3)
    rows = (await db.execute(
        select(InboxMessage.sender_phone)
        .where(InboxMessage.instance_id == instance_id,
               InboxMessage.received_at >= cutoff,
               InboxMessage.is_group.is_(False),
               InboxMessage.sender_phone.isnot(None))
        .order_by(InboxMessage.received_at.desc())
    )).scalars().all()
    seen, out = set(), []
    for p in rows:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
        if len(out) >= limit:
            break
    return out


async def process_warmup_accounts(db, now: datetime | None = None) -> dict:
    """Daily driver: advance each auto-warming account and send its (small) reply quota."""
    now = now or datetime.utcnow()
    accounts = (await db.execute(
        select(Account).where(Account.auto_warmup.is_(True), Account.warmup_completed.is_(False))
    )).scalars().all()

    completed = warmed = sent_total = 0
    for acc in accounts:
        if not acc.warmup_started_at:
            acc.warmup_started_at = now      # safety: stamp start on first run
        day = warmup_day(acc, now)
        if day > WARMUP_TOTAL_DAYS:
            acc.warmup_completed = True
            completed += 1
            continue
        limit = warmup_daily_limit(day)
        if limit == 0 or acc.status != AccountStatus.active:
            continue                          # receive-only phase or not connected
        warmed += 1
        phones = await _recent_inbound_phones(acc.instance_id, db, limit)
        if not phones:
            continue
        client = GreenAPIClient(acc.instance_id, acc.api_token)
        import random
        for i, phone in enumerate(phones[:limit]):
            try:
                await client.send_message(phone, random.choice(WARMUP_TEMPLATES))
                sent_total += 1
            except Exception as e:
                logger.warning("warm-up send failed for %s: %s", acc.instance_id, e)
    await db.commit()
    logger.info("auto warm-up: warmed=%d completed=%d sent=%d", warmed, completed, sent_total)
    return {"warmed": warmed, "completed": completed, "sent": sent_total}
