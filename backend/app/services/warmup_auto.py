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
# V16 PART 5 — how many messages a single beat run may send per account (the rest wait
# for the next run, spreading warm-up sends across the day). The DAILY cap is still the
# hard ceiling, enforced via a Redis per-day counter.
PER_RUN_CAP = 2

# Default warm-up phrase pool (seeded into warmup_phrases on first boot; editable after).
DEFAULT_PHRASES = [
    "سلام، خوب هستید؟",
    "سلام، ممنون از پیامتان. در خدمتیم. 🌟",
    "با تشکر از پیام شما، بله در خدمتیم.",
    "سلام و درود، پیام شما دریافت شد. خوشحال می‌شویم کمکتان کنیم.",
    "ممنون از تماس شما. در اسرع وقت پاسخگو هستیم.",
    "سلام، امیدوارم حالتان خوب باشد. کمکی از دست ما برمی‌آید؟",
    "ممنون از خریدتان. اگر سوالی بود در خدمتیم.",
    "سلام، روز خوبی داشته باشید. 🌷",
    "بله موجود است، در خدمت شما هستیم.",
    "سلام، ممنون که با ما در ارتباط هستید.",
    "درود بر شما، پیامتان را دیدیم و پاسخگو هستیم.",
    "ممنون از پیام شما، در اولین فرصت بررسی می‌کنیم.",
]
# Backward-compatible fallback (used only if the DB phrase table is empty/unreadable).
WARMUP_TEMPLATES = DEFAULT_PHRASES[:5]


async def get_active_phrases(db) -> list[str]:
    """Active phrases from the editable pool; falls back to the built-in DEFAULT_PHRASES
    whenever the table is empty OR unreadable, so warm-up NEVER depends on the DB seed."""
    try:
        from sqlalchemy import select
        from app.models.warmup import WarmupPhrase
        rows = (await db.execute(
            select(WarmupPhrase.text).where(WarmupPhrase.is_active.is_(True))
        )).scalars().all()
        phrases = [t for t in rows if t and t.strip()]
        return phrases or list(DEFAULT_PHRASES)
    except Exception:
        return list(DEFAULT_PHRASES)


# ── Redis per-day sent counter (enforces the daily cap across multiple runs) ──
def _sent_key(account_id: str) -> str:
    import pytz
    from datetime import datetime as _dt
    day = _dt.now(pytz.timezone("Asia/Tehran")).strftime("%Y%m%d")
    return f"warmup_sent:{account_id}:{day}"


async def warmup_sent_today(account_id: str) -> int:
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        return int(await r.get(_sent_key(account_id)) or 0)
    except Exception:
        return 0


async def record_warmup_send(account_id: str):
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        key = _sent_key(account_id)
        pipe = r.pipeline()
        pipe.incr(key); pipe.expire(key, 172800)
        await pipe.execute()
    except Exception:
        pass


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


def _to_send_this_run(daily_limit: int, sent_today: int, per_run_cap: int = PER_RUN_CAP) -> int:
    """How many messages this run may send: bounded by the remaining DAILY allowance AND
    the per-run cap. Pure (unit-testable) — this is the anti-overshoot guard."""
    remaining = max(0, int(daily_limit) - int(sent_today))
    return max(0, min(int(per_run_cap), remaining))


async def process_warmup_accounts(db, now: datetime | None = None, jitter: bool = True) -> dict:
    """Runs several times a day (see beat schedule). Advances each auto-warming account and
    sends a SMALL portion of its daily reply quota, spread across runs with jitter. The daily
    cap is enforced via a Redis per-day counter, so batch + timing can never overshoot it."""
    import asyncio
    import random
    now = now or datetime.utcnow()
    accounts = (await db.execute(
        select(Account).where(Account.auto_warmup.is_(True), Account.warmup_completed.is_(False))
    )).scalars().all()
    # V18 PART 2 — defer to the V17 mesh: never legacy-warm a number that has a
    # warmup_enrollment (the toggle now creates one and clears auto_warmup, but guard
    # anyway so the two engines can never double-warm the same number).
    try:
        from app.services.warmup_exclusion import enrolled_instance_ids
        enrolled = await enrolled_instance_ids(db)
        if enrolled:
            accounts = [a for a in accounts if a.instance_id not in enrolled]
    except Exception:
        pass
    phrases = await get_active_phrases(db)

    completed = warmed = sent_total = 0
    for acc in accounts:
        if not acc.warmup_started_at:
            acc.warmup_started_at = now      # safety: stamp start on first run
        day = warmup_day(acc, now)
        if day > WARMUP_TOTAL_DAYS:
            acc.warmup_completed = True
            completed += 1
            continue
        daily_limit = warmup_daily_limit(day)
        if daily_limit == 0 or acc.status != AccountStatus.active:
            continue                          # receive-only phase or not connected
        sent_today = await warmup_sent_today(str(acc.id))
        to_send = _to_send_this_run(daily_limit, sent_today)
        if to_send == 0:
            continue                          # daily cap already reached — never exceed it
        warmed += 1
        # Reply-first guardrail: only message numbers that contacted this account first.
        phones = await _recent_inbound_phones(acc.instance_id, db, to_send)
        if not phones:
            continue
        client = GreenAPIClient(acc.instance_id, acc.api_token)
        for phone in phones[:to_send]:
            # Re-check the cap right before each send (defends against races/batch).
            if await warmup_sent_today(str(acc.id)) >= daily_limit:
                break
            try:
                await client.send_message(phone, random.choice(phrases))
                await record_warmup_send(str(acc.id))
                sent_total += 1
                if jitter:
                    await asyncio.sleep(random.uniform(3, 12))  # human-like gap between sends
            except Exception as e:
                logger.warning("warm-up send failed for %s: %s", acc.instance_id, e)
    await db.commit()
    logger.info("auto warm-up: warmed=%d completed=%d sent=%d", warmed, completed, sent_total)
    return {"warmed": warmed, "completed": completed, "sent": sent_total}
