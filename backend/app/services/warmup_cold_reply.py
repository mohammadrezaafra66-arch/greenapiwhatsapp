"""V29 «همکاری تیمی» PART 5 — automatic contextual reply FROM the cold account.

When a contact sends the requested message to a cold account (detected on the webhook, PART 4),
the COLD ACCOUNT itself sends ONE natural, contextual reply back to the contact — continuing the
thread's topic (e.g. "بله همین الان برات فرستادم، ممنون که پیگیری کردی"). This is NOT an
open-ended chatbot: exactly one reply per scheduled ask-step.

Non-negotiable safety (guardrail 6): the cold account's reply routes through the SAME rails as
every other send —
  • V27 `can_send_now`/`gate_check` (status / cooldown_until / throttle / live yellowCard), AND
  • the cold account's own 24h post-authorization cooldown (the SAME clock the mesh uses), AND
  • the shared per-instance `peer_pacer`.
If the cold account is within its 24h cooldown or otherwise unhealthy, the reply is DEFERRED
until it is eligible. The reply is scheduled for a natural delay (never instant), and its text
passes the exact V24 identifier-leak filter.
"""
from __future__ import annotations
import logging
import random
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_helpers import WarmupHelper, WarmupHelperThread
from app.services.green_api import GreenAPIClient
from app.services.warmup_content import message_is_safe
from app.services import warmup_helper_thread as wt
from app.services import peer_pacer
from app.services.warmup_helper_engine import _to_utc_naive, _send_from_main, _default_client_factory
from app.services.warmup_scheduler import TEHRAN

logger = logging.getLogger("afrakala.warmup.coldreply")

# Natural delay before the cold account replies (never instant). Jittered within [min, max].
COLD_REPLY_MIN_DELAY_SECONDS = 120     # 2 min floor
COLD_REPLY_MAX_DELAY_SECONDS = 600     # 10 min ceiling


def cold_reply_delay_seconds(rng: random.Random | None = None) -> float:
    return (rng or random).uniform(COLD_REPLY_MIN_DELAY_SECONDS, COLD_REPLY_MAX_DELAY_SECONDS)


def cold_reply_due_at(now: datetime, rng: random.Random | None = None) -> datetime:
    """When the cold account's auto-reply becomes due: now + a jittered natural delay."""
    return now + timedelta(seconds=cold_reply_delay_seconds(rng))


# ── 24h post-auth cooldown (reuse the mesh clock) ─────────────────────────────
def post_auth_cooldown_elapsed(enrollment, now: datetime | None = None) -> bool:
    """True when the cold account's mandatory 24h post-authorization cooldown has cleared. Reuses
    the mesh's own cooldown math. A missing/unknown authorization is treated as NOT elapsed
    (conservative — never send during an unknown cooldown)."""
    from app.services.warmup_mesh_service import cooldown_elapsed
    if enrollment is None:
        return False
    return cooldown_elapsed(enrollment, now=now)


def cold_account_ready(account, enrollment, now: datetime | None = None) -> tuple[bool, str]:
    """PURE gate for a cold-account send: the V27 health gate AND the 24h post-auth cooldown.
    Returns (ready, reason)."""
    from app.services.send_gate import can_send_now
    now = now or datetime.utcnow()
    if not post_auth_cooldown_elapsed(enrollment, now):
        return False, "cooldown_24h"
    allowed, reason = can_send_now(account, None, now)
    if not allowed:
        return False, reason
    return True, "ok"


# ── reply generation (leak-filtered; continues the topic) ────────────────────
def _system_prompt() -> str:
    return (
        "تو یک فروشندهٔ فارسی‌زبان دوستانه هستی که به پیام یک همکار/مشتری پاسخ کوتاه و طبیعی می‌دهی. "
        "پاسخ باید ادامهٔ همان موضوع گفت‌وگو باشد، صمیمی و انسانی، نه رباتیک. "
        "هرگز شماره تلفن، عدد بلند، شناسه یا لینک ننویس — فقط یک پاسخ کوتاه محاوره‌ای فارسی."
    )


def _user_prompt(topic: str, contact_name: str) -> str:
    return (
        f"یک همکار به نام «{contact_name}» دربارهٔ «{topic}» به تو پیام داده. "
        f"یک پاسخ کوتاه، صمیمی و طبیعی فارسی بده که همان موضوع را ادامه دهد و تشکر/جمع‌بندی طبیعی داشته باشد. "
        f"کوتاه (یک جمله)، بدون هیچ عدد یا لینک یا شماره. فقط متن پاسخ را بده."
    )


def build_cold_reply_ai_fn(chat_fn=None):
    async def _ai(*, topic: str, contact_name: str):
        fn = chat_fn
        if fn is None:
            from app.services.gpt_service import _chat
            fn = _chat
        try:
            return await fn(_system_prompt(), _user_prompt(topic, contact_name), 70, 0.9)
        except Exception as e:  # pragma: no cover
            logger.debug("cold-reply AI chat failed, will fall back: %s", e)
            return None
    return _ai


_FALLBACK = [
    "سلام، آره همین الان برات فرستادم، ممنون که پیگیری کردی 🙏",
    "قربانت، انجام شد؛ اگه چیزی لازم داشتی بگو 🌹",
    "بله حتماً، ممنون از پیگیریت 👍",
    "دمت گرم، ترتیبش داده شد؛ خبرت می‌کنم 🙏",
    "سلام، آره حواسم هست؛ ممنون که یادآوری کردی 🌷",
]


def build_cold_reply_fallback(rng: random.Random | None = None) -> str:
    return (rng or random).choice(_FALLBACK)


async def generate_cold_reply(*, topic: str, contact_name: str, ai_fn=None, forbidden=(),
                              rng: random.Random | None = None, max_ai_tries: int = 2) -> tuple[str, str]:
    """Generate ONE cold-account reply text. Returns (text, source ∈ {ai,fallback}). Every
    candidate passes the V24 identifier-leak filter; a safe templated fallback is always available."""
    r = rng or random
    if ai_fn is not None:
        for _ in range(max_ai_tries):
            try:
                text = await ai_fn(topic=topic, contact_name=contact_name)
            except Exception:
                break
            text = (text or "").strip()
            if text and message_is_safe(text, forbidden):
                return text, "ai"
    # safe fallback
    for _ in range(len(_FALLBACK) + 1):
        cand = build_cold_reply_fallback(r)
        if message_is_safe(cand, forbidden):
            return cand, "fallback"
    return "ممنون از پیگیریت 🙏", "fallback"


# ── the tick: send ONE due, eligible cold reply ──────────────────────────────
def _default_factory(instance_id: str, api_token: str) -> GreenAPIClient:
    return GreenAPIClient(instance_id, api_token)


async def run_cold_reply_tick(db, now: datetime | None = None, *, client_factory=None,
                              ai_fn=None, rng: random.Random | None = None) -> dict:
    """Send AT MOST one due cold-account auto-reply this tick, fully gated. Threads whose cold
    account is not yet eligible are left pending (deferred until eligible). Returns a summary."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.now(TEHRAN).replace(tzinfo=None)
    r = rng or random

    due = (await db.execute(
        select(WarmupHelperThread).where(
            WarmupHelperThread.awaiting_reply.is_(True),
            WarmupHelperThread.status == wt.STATUS_ACTIVE,
            WarmupHelperThread.pending_reply_at.isnot(None),
            WarmupHelperThread.pending_reply_at <= now,
        ).order_by(WarmupHelperThread.pending_reply_at)
    )).scalars().all()
    if not due:
        return {"acted": 0, "due": 0}

    from app.models.warmup_mesh import WarmupEnrollment
    for thread in due:
        cold = (await db.execute(
            select(Account).where(Account.instance_id == thread.cold_instance_id)
        )).scalar_one_or_none()
        helper = await db.get(WarmupHelper, thread.helper_id)
        if cold is None or helper is None:
            # orphaned — clear the pending flag so it doesn't spin forever
            thread.awaiting_reply = False
            thread.pending_reply_at = None
            continue
        enr = (await db.execute(
            select(WarmupEnrollment).where(WarmupEnrollment.instance_id == thread.cold_instance_id)
        )).scalar_one_or_none()

        ready, reason = cold_account_ready(cold, enr, now)
        pacer_now = _to_utc_naive(now)
        if not ready or not peer_pacer.peer_ready(cold.instance_id, pacer_now):
            # defer this one — leave it pending; a later tick retries once eligible.
            continue

        topic = thread.topic_summary or "پیگیری سفارش"
        forbidden = tuple(v for v in (thread.cold_instance_id, getattr(cold, "name", None),
                                      helper.sender_instance_id) if v)
        text, source = await generate_cold_reply(
            topic=topic, contact_name=helper.name,
            ai_fn=ai_fn if ai_fn is not None else build_cold_reply_ai_fn(),
            forbidden=forbidden, rng=r)

        # _send_from_main re-applies the V27 live health gate on the COLD account before hitting
        # Green API — same rail as every other send, never a parallel path.
        mid = await _send_from_main(cold, helper.phone, text, client_factory)

        thread.awaiting_reply = False
        thread.pending_reply_at = None
        wt.advance_thread(thread, topic, now)      # count the cold reply as a step; keep topic
        from app.services import warmup_helper_log as tclog
        tclog.record(db, event_type=tclog.EVENT_COLD_REPLY, from_instance_id=cold.instance_id,
                     to_phone=helper.phone, helper_id=helper.id,
                     sender_instance_id=helper.sender_instance_id,
                     cold_instance_id=thread.cold_instance_id, thread_id=thread.id,
                     message_sent=text)
        if mid:
            peer_pacer.record_peer_send(cold.instance_id, pacer_now, r)
        await db.commit()
        return {"acted": 1, "due": len(due), "cold_instance_id": thread.cold_instance_id,
                "helper": helper.name, "sent": bool(mid), "source": source, "reason": "sent"}

    await db.commit()
    return {"acted": 0, "due": len(due), "deferred": True}
