"""V29 «همکاری تیمی» PART 9 — the dedicated event log (Shamsi dates).

A log SEPARATE from the regular inbox/send-queue: one row per «همکاری تیمی» event
(ask / reminder / thank-you / cold-reply / incoming / safety-flag), recording which account sent
what to which account and what was received. Displayed on its own page with Shamsi dates + exact
Tehran times, filterable by sender / contact / cold account.

`record()` is best-effort and does NOT commit (the caller's session commits), so wiring it into a
send path can never break that path. `list_events()` renders each row with the shared Shamsi
utility.
"""
from __future__ import annotations
import logging
from sqlalchemy import select

from app.models.warmup_helpers import WarmupHelperLog
from app.utils.shamsi import to_shamsi

logger = logging.getLogger("afrakala.warmup.log")

# Event types.
EVENT_ASK = "ask"
EVENT_REMINDER = "reminder"
EVENT_THANK_YOU = "thank_you"
EVENT_COLD_REPLY = "cold_reply"
EVENT_INCOMING = "incoming"
EVENT_SAFETY = "safety_flag"

EVENT_TYPES = (EVENT_ASK, EVENT_REMINDER, EVENT_THANK_YOU, EVENT_COLD_REPLY,
               EVENT_INCOMING, EVENT_SAFETY)

EVENT_FA = {
    EVENT_ASK: "درخواست",
    EVENT_REMINDER: "یادآوری",
    EVENT_THANK_YOU: "تشکر",
    EVENT_COLD_REPLY: "پاسخ اکانت سرد",
    EVENT_INCOMING: "پیام دریافتی",
    EVENT_SAFETY: "هشدار ایمنی",
}


def record(db, *, event_type: str, from_instance_id: str | None = None, to_phone: str | None = None,
           helper_id=None, sender_instance_id: str | None = None, cold_instance_id: str | None = None,
           thread_id=None, message_sent: str | None = None,
           message_received: str | None = None) -> WarmupHelperLog | None:
    """Add ONE «همکاری تیمی» log row (best-effort, no commit). Returns the row or None on error."""
    try:
        row = WarmupHelperLog(
            event_type=event_type, from_instance_id=from_instance_id,
            to_phone=to_phone, helper_id=helper_id, sender_instance_id=sender_instance_id,
            cold_instance_id=cold_instance_id, thread_id=thread_id,
            message_sent=message_sent, message_received=message_received)
        db.add(row)
        return row
    except Exception as e:  # pragma: no cover
        logger.warning("team-collab log record failed (non-fatal): %s", e)
        return None


async def list_events(db, *, sender_instance_id: str | None = None, cold_instance_id: str | None = None,
                      helper_id=None, event_type: str | None = None, limit: int = 200) -> list[dict]:
    """The log rows (newest first), filtered by sender / cold account / contact / event type, each
    rendered with a Shamsi date + exact Tehran time."""
    q = select(WarmupHelperLog)
    if sender_instance_id:
        q = q.where(WarmupHelperLog.sender_instance_id == sender_instance_id)
    if cold_instance_id:
        q = q.where(WarmupHelperLog.cold_instance_id == cold_instance_id)
    if helper_id:
        q = q.where(WarmupHelperLog.helper_id == helper_id)
    if event_type:
        q = q.where(WarmupHelperLog.event_type == event_type)
    q = q.order_by(WarmupHelperLog.created_at.desc()).limit(min(limit, 1000))
    rows = (await db.execute(q)).scalars().all()
    return [render_row(r) for r in rows]


async def recent_ask_bodies(db, sender_instance_id: str | None, limit: int = 8) -> list[str]:
    """V30 PART 5 — the first lines (bodies) of a sender's most-recent ASK messages, fed as
    `recent` into the ask generator so consecutive asks are never near-duplicates. Best-effort:
    returns [] when the sender id is missing or nothing is logged yet."""
    if not sender_instance_id:
        return []
    rows = (await db.execute(
        select(WarmupHelperLog).where(
            WarmupHelperLog.sender_instance_id == sender_instance_id,
            WarmupHelperLog.event_type == EVENT_ASK,
            WarmupHelperLog.message_sent.isnot(None),
        ).order_by(WarmupHelperLog.created_at.desc()).limit(min(limit, 50))
    )).scalars().all()
    return [str(getattr(r, "message_sent", "")).split("\n", 1)[0]
            for r in rows if getattr(r, "message_sent", None)]


def render_row(r) -> dict:
    """PURE-ish — one log row as a display dict with the Shamsi date/time."""
    return {
        "id": str(r.id),
        "event_type": r.event_type,
        "event_fa": EVENT_FA.get(r.event_type, r.event_type),
        "from_instance_id": r.from_instance_id,
        "to_phone": r.to_phone,
        "helper_id": str(r.helper_id) if r.helper_id else None,
        "sender_instance_id": r.sender_instance_id,
        "cold_instance_id": r.cold_instance_id,
        "thread_id": str(r.thread_id) if r.thread_id else None,
        "message_sent": r.message_sent,
        "message_received": r.message_received,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "shamsi": to_shamsi(r.created_at),      # Shamsi date + exact Tehran time
    }
