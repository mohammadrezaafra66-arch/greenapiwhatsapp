"""V30 PART 5 — AI-generated, varied, emoji, STAGGERED thank-you messages.

V29 sent a single STATIC Persian thank-you line inline. V30:
  • makes the thank-you AI-generated, warm/positive-toned, VARIED per send (same anti-repeat +
    emoji guidance as ask-messages), passing the exact V24 identifier-leak filter;
  • STAGGERS bursts — when one contact completes several tasks near-simultaneously, the sender's
    per-instance `peer_pacer` isn't ready for the 2nd/3rd, so those are SCHEDULED (awaiting_thankyou
    + pending_thankyou_at) and sent later by `run_thankyou_tick`, one per tick, paced + inside the
    09:00–19:00 Tehran window. The FIRST completion still gets an immediate inline thank-you (the
    engine handles that); only the overflow is deferred, so no burst of simultaneous thank-yous.

Pure pieces (`thankyou_due_at`, `generate_thank_you`) are rng/now-injectable for unit tests.
"""
from __future__ import annotations
import logging
import random
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_helpers import WarmupHelper, WarmupHelperThread
from app.services.warmup_content import message_is_safe, is_near_duplicate, has_emoji
from app.services import warmup_helper_thread as wt
from app.services import peer_pacer
from app.services.warmup_helper_engine import _to_utc_naive, _send_from_main, _default_client_factory
from app.services.warmup_scheduler import TEHRAN

logger = logging.getLogger("afrakala.warmup.thankyou")

# A small base delay (never instant) before a deferred thank-you becomes due.
THANKYOU_BASE_DELAY_SECONDS = 20


def thankyou_due_at(now: datetime, ahead_count: int = 0,
                    rng: random.Random | None = None) -> datetime:
    """When a DEFERRED thank-you becomes due: now + base + a jittered per-instance-floor gap for
    each thank-you already queued ahead of it for this sender. Consecutive due times are therefore
    at least the anti-ban floor apart, so the tick never fires a burst."""
    r = rng or random
    gap = peer_pacer.jittered_gap_seconds(r)
    return now + timedelta(seconds=THANKYOU_BASE_DELAY_SECONDS + max(0, int(ahead_count)) * gap)


# ── content generation (AI-first, varied, emoji, leak-filtered) ──────────────
def _system_prompt() -> str:
    return (
        "تو یک فروشندهٔ فارسی‌زبان صمیمی هستی که از یک همکار بابت یک لطف کوچک تشکر می‌کنی. "
        "یک پیام تشکر کوتاه، گرم، مثبت و کاملاً طبیعی بنویس؛ هر بار متفاوت و غیرتکراری. "
        "یکی دو ایموجی مناسب و طبیعی به‌کار ببر (نه زیاد). "
        "هرگز شماره تلفن، عدد بلند، شناسه یا لینک ننویس — فقط متن کوتاه تشکر فارسی."
    )


def _user_prompt(contact_name: str) -> str:
    return (
        f"از «{contact_name}» بابت لطفش تشکر کن. یک جملهٔ کوتاه، صمیمی و مثبت با یکی دو ایموجی. "
        f"بدون هیچ عدد یا لینک. فقط متن پیام را بده."
    )


def build_thankyou_ai_fn(chat_fn=None):
    async def _ai(*, contact_name: str):
        fn = chat_fn
        if fn is None:
            from app.services.gpt_service import _chat
            fn = _chat
        try:
            return await fn(_system_prompt(), _user_prompt(contact_name), 60, 0.95)
        except Exception as e:  # pragma: no cover
            logger.debug("thank-you AI chat failed, will fall back: %s", e)
            return None
    return _ai


# Varied templated fallbacks — each is distinct, carries a natural emoji, contains a «ممنون»
# thanks marker, and leaks no identifier.
_FALLBACK = [
    "ممنون از لطفت {name} 🙏",
    "دمت گرم {name} جان، ممنونم که کمک کردی 🌹",
    "قربونت {name}، ممنون که وقت گذاشتی 👍",
    "مرسی و ممنون {name} عزیز، لطف کردی 😊",
    "سپاس {name} جان، خیلی ممنونم 🌷",
]


def build_thankyou_fallback(name: str | None, rng: random.Random | None = None) -> str:
    r = rng or random
    who = (name or "").strip()
    return r.choice(_FALLBACK).replace("{name}", who).replace("  ", " ").strip()


async def generate_thank_you(*, contact_name: str, ai_fn=None, forbidden=(),
                             recent: list[str] | None = None, rng: random.Random | None = None,
                             max_ai_tries: int = 2) -> tuple[str, str]:
    """Generate ONE thank-you. Returns (text, source ∈ {ai,fallback}). Every candidate passes the
    V24 identifier-leak filter and the anti-repeat check; AI candidates are additionally preferred
    to carry emoji (regenerate once if missing). A safe, emoji-bearing fallback is always available."""
    recent = recent or []
    r = rng or random
    if ai_fn is not None:
        for _ in range(max_ai_tries):
            try:
                text = await ai_fn(contact_name=contact_name)
            except Exception:
                break
            text = (text or "").strip()
            if not text:
                continue
            if not message_is_safe(text, forbidden):
                continue
            if is_near_duplicate(text, recent):
                continue
            if not has_emoji(text):          # prefer emoji; try again, else fall through
                continue
            return text, "ai"
    for _ in range(len(_FALLBACK) + 1):
        cand = build_thankyou_fallback(contact_name, r)
        if message_is_safe(cand, forbidden) and not is_near_duplicate(cand, recent):
            return cand, "fallback"
    return build_thankyou_fallback(contact_name, r), "fallback"


# ── the tick: send ONE due, paced, in-window thank-you ───────────────────────
async def run_thankyou_tick(db, now: datetime | None = None, *, client_factory=None,
                            ai_fn=None, rng: random.Random | None = None) -> dict:
    """Send AT MOST one due, deferred thank-you this tick — gated by the 09:00–19:00 Tehran window,
    the sender's health gate, and the shared per-instance pacer. Others stay queued (staggered)."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.now(TEHRAN).replace(tzinfo=None)
    r = rng or random

    from app.services.warmup_team_hours import in_team_hours
    if not in_team_hours(now):
        return {"acted": 0, "in_team_hours": False}

    due = (await db.execute(
        select(WarmupHelperThread).where(
            WarmupHelperThread.awaiting_thankyou.is_(True),
            WarmupHelperThread.pending_thankyou_at.isnot(None),
            WarmupHelperThread.pending_thankyou_at <= now,
        ).order_by(WarmupHelperThread.pending_thankyou_at)
    )).scalars().all()
    if not due:
        return {"acted": 0, "due": 0}

    for thread in due:
        helper = await db.get(WarmupHelper, thread.helper_id)
        if helper is None:
            thread.awaiting_thankyou = False
            thread.pending_thankyou_at = None
            continue
        enr_map = {}
        accounts = (await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )).scalars().all()
        from app.services.warmup_helper_engine import resolve_task_sender
        sender = resolve_task_sender(accounts, helper, enr_map)
        if sender is None:
            thread.awaiting_thankyou = False
            thread.pending_thankyou_at = None
            continue

        if not peer_pacer.thankyou_ready(sender.instance_id, now):
            # a thank-you from this sender just went out — defer THIS one; a later tick retries,
            # keeping thank-yous staggered by at least the anti-ban floor.
            continue

        forbidden = tuple(v for v in (thread.cold_instance_id, getattr(sender, "name", None),
                                      helper.sender_instance_id) if v)
        text, source = await generate_thank_you(
            contact_name=helper.name,
            ai_fn=ai_fn if ai_fn is not None else build_thankyou_ai_fn(),
            forbidden=forbidden, rng=r)
        mid = await _send_from_main(sender, helper.phone, text, client_factory)

        thread.awaiting_thankyou = False
        thread.pending_thankyou_at = None
        from app.services import warmup_helper_log as tclog
        tclog.record(db, event_type=tclog.EVENT_THANK_YOU, from_instance_id=sender.instance_id,
                     to_phone=helper.phone, helper_id=helper.id,
                     sender_instance_id=getattr(sender, "instance_id", None),
                     cold_instance_id=thread.cold_instance_id, thread_id=thread.id, message_sent=text)
        if mid:
            peer_pacer.record_thankyou(sender.instance_id, now, r)
        await db.commit()
        return {"acted": 1, "due": len(due), "helper": helper.name,
                "sender_instance_id": sender.instance_id, "sent": bool(mid), "source": source}

    await db.commit()
    return {"acted": 0, "due": len(due), "deferred": True}
