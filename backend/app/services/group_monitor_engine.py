"""V26 — orchestration for a newly-captured group message.

Single stable entry point called by the webhook after ingest:
  • PART 2: the webhook has one call site; ingest-only.
  • PART 3: text messages run keyword detection + optional auto-reply here.
  • PART 4: voice messages are enqueued for transcription, then detected on the transcript
    via the SAME run_detection_and_reply path.

Kept fully guarded so it can never disrupt the webhook loop. Auto-reply is OFF by default
and only fires when the group has auto_reply_enabled AND conversation_mode != off, inside
waking hours (09:00–21:00 Tehran), under a jittered per-group hourly rate limit, with the
V24 no-identifier-leak safeguard on every outgoing reply.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.group_monitor import (
    GroupMessage, GroupKeyword, GroupPredefinedReply, MonitoredGroup, GroupForbiddenAlert,
    CONVERSATION_MODE_OFF, CONVERSATION_MODE_PREDEFINED, CONVERSATION_MODE_AI,
)
from app.services.group_detection import (
    detect, select_predefined_reply, within_rate_limit, should_auto_reply,
)
from app.services.warmup_scheduler import in_active_hours
from app.services.typing_sim import apply_typing_simulation

logger = logging.getLogger("afrakala.group_monitor")

RATE_WINDOW = timedelta(hours=1)


async def handle_new_group_message(gm_id: str) -> None:
    """Dispatch a freshly-ingested group_message: a voice note (PART 4) is enqueued for
    transcription (detection then runs on the transcript); a text message runs detection +
    optional auto-reply immediately."""
    async with AsyncSessionLocal() as db:
        gm = await db.get(GroupMessage, uuid.UUID(gm_id))
        if not gm:
            return
        if gm.is_voice and gm.transcription_status == "pending":
            _enqueue_transcription(gm_id)
            return
        if gm.text:
            await run_detection_and_reply(db, gm, gm.text)


def _enqueue_transcription(gm_id: str) -> None:
    """PART 4 — hand the voice note to the Celery transcription task (webhook stays fast).
    Guarded: if the worker/broker isn't reachable the webhook must not fail."""
    try:
        from app.workers.tasks import task_transcribe_group_voice
        task_transcribe_group_voice.delay(gm_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("could not enqueue transcription for %s: %s", gm_id, e)


async def _recent_reply_count(db, group_id: str) -> int:
    since = datetime.utcnow() - RATE_WINDOW
    n = await db.execute(
        select(func.count()).select_from(GroupMessage).where(
            GroupMessage.group_id == group_id,
            GroupMessage.replied.is_(True),
            GroupMessage.created_at >= since,
        )
    )
    return int(n.scalar() or 0)


async def run_detection_and_reply(db, gm: GroupMessage, text: str) -> dict:
    """Detect trigger/forbidden keywords in `text`, persist results, raise admin alerts for
    forbidden words, and (only if enabled) send one auto-reply. Shared by the text path
    (PART 3) and the voice-transcript path (PART 4). Returns a small summary dict.

    Commits its own changes; fully guarded so a send failure never loses the stored detection.
    """
    keywords = (await db.execute(
        select(GroupKeyword).where(GroupKeyword.active.is_(True))
    )).scalars().all()
    triggers, forbidden = detect(text, keywords)

    gm.matched_keywords = ", ".join(triggers) if triggers else None
    if forbidden:
        gm.flagged_forbidden = True

    # Forbidden words → admin-visible alert rows (NEVER an auto-message to anyone).
    for word in forbidden:
        db.add(GroupForbiddenAlert(
            listener_instance_id=gm.listener_instance_id,
            group_id=gm.group_id, group_name=gm.group_name,
            sender=gm.sender, sender_name=gm.sender_name,
            word=word, message_text=(text or "")[:1000], group_message_id=gm.id,
        ))

    summary = {"triggers": triggers, "forbidden": forbidden, "replied": False}

    # Auto-reply gate (default OFF). Only proceeds for a monitored group whose auto-reply is
    # enabled and conversation_mode != off, with a matched trigger, in waking hours, under
    # the jittered per-group hourly cap.
    mg = (await db.execute(
        select(MonitoredGroup).where(
            MonitoredGroup.listener_instance_id == gm.listener_instance_id,
            MonitoredGroup.group_id == gm.group_id,
        )
    )).scalar_one_or_none()

    if mg and triggers:
        recent = await _recent_reply_count(db, gm.group_id)
        gate = should_auto_reply(
            auto_reply_enabled=bool(mg.auto_reply_enabled),
            conversation_mode=mg.conversation_mode,
            has_trigger=bool(triggers),
            in_waking_hours=in_active_hours(datetime.now()),
            within_rate=within_rate_limit(recent),
        )
        if gate:
            reply_text = await _build_reply(db, gm, mg, triggers, text)
            if reply_text and await _send_reply(db, gm, reply_text):
                gm.replied = True
                summary["replied"] = True

    await db.commit()
    return summary


async def _build_reply(db, gm: GroupMessage, mg: MonitoredGroup, triggers, text: str):
    """Pick the reply text per conversation_mode. predefined → matching/default canned reply;
    ai → a safe generated Persian reply, falling back to the predefined/default reply."""
    predefined = await _predefined_reply(db, triggers)
    if mg.conversation_mode == CONVERSATION_MODE_PREDEFINED:
        return predefined
    if mg.conversation_mode == CONVERSATION_MODE_AI:
        from app.services.group_ai_reply import generate_ai_reply
        # Forbidden set for the leak-safeguard: this listener's own identifiers.
        forbidden = _identifier_guard(gm)
        history = await _recent_group_texts(db, gm.group_id, exclude_id=gm.id)
        ai = await generate_ai_reply(text, history=history, forbidden=forbidden)
        return ai or predefined
    return None


async def _predefined_reply(db, triggers):
    replies = (await db.execute(
        select(GroupPredefinedReply).where(GroupPredefinedReply.active.is_(True))
    )).scalars().all()
    # Map matched trigger words → their keyword ids so a keyword-specific reply can win.
    kws = (await db.execute(
        select(GroupKeyword).where(GroupKeyword.active.is_(True))
    )).scalars().all()
    keyword_id_by_word = {k.word: k.id for k in kws}
    return select_predefined_reply(triggers, replies, keyword_id_by_word)


async def _recent_group_texts(db, group_id: str, exclude_id, limit: int = 6):
    rows = (await db.execute(
        select(GroupMessage).where(
            GroupMessage.group_id == group_id,
            GroupMessage.id != exclude_id,
        ).order_by(GroupMessage.created_at.desc()).limit(limit)
    )).scalars().all()
    texts = [r.text or r.transcription for r in rows]
    return [t for t in texts if t]


def _identifier_guard(gm: GroupMessage) -> tuple:
    """Identifiers that must never leak into a reply (this listener's instance id)."""
    return tuple(x for x in (gm.listener_instance_id,) if x)


async def _send_reply(db, gm: GroupMessage, reply_text: str) -> bool:
    """Send the auto-reply FROM the listener instance to the group chatId, honoring typing
    simulation + send delay. Best-effort: returns True only on a successful send."""
    acc = (await db.execute(
        select(Account).where(Account.instance_id == gm.listener_instance_id)
    )).scalar_one_or_none()
    if not acc:
        return False
    try:
        from app.services.green_api import GreenAPIClient
        client = GreenAPIClient(acc.instance_id, acc.api_token)
        # Typing/recording indicator for a length-scaled, jittered duration (anti-ban).
        await apply_typing_simulation(client, gm.group_id, reply_text)
        msg_id = await client.send_group_message(gm.group_id, reply_text)
        return bool(msg_id)
    except Exception as e:
        logger.warning("group auto-reply send failed (non-fatal): %s", e)
        return False
