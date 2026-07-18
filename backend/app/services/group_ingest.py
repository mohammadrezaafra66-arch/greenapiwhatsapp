"""V26 PART 2 — ingest incoming GROUP messages on monitored groups.

Called as an ADDITIVE branch from the existing incoming-webhook handler. It never replaces
or slows the existing inbox/campaign/warm-up processing: private (@c.us) messages continue
to flow to the inbox exactly as before; this only captures group (@g.us) messages that
belong to a LISTENER instance and a monitored group, deduped on Green API idMessage.

`extract_group_message_fields` is pure (no DB/network) so it unit-tests against the verified
Green API webhook shapes. `ingest_group_message` opens its own session and is fully guarded
by the caller so a malformed payload can never disrupt the webhook loop.
"""
from __future__ import annotations
import logging
from datetime import datetime
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.group_monitor import (
    MonitoredGroup, GroupMessage, TRANSCRIPTION_NONE, TRANSCRIPTION_PENDING,
)

logger = logging.getLogger("afrakala.group_ingest")


def is_group_chat(chat_id: str | None, platform: str = "whatsapp") -> bool:
    """A chat is a GROUP: WhatsApp → ends '@g.us'; Telegram → a negative-number chatId."""
    from app.services.platforms import is_group_chat_id
    return is_group_chat_id(chat_id, platform)


def extract_group_message_fields(payload: dict) -> dict:
    """Pure extraction of the group_message fields from a verified Green API
    `incomingMessageReceived` payload. Returns a dict ready to build a GroupMessage.

    Text: textMessage → textMessageData.textMessage; extendedTextMessage →
    extendedTextMessageData.text; other media → its caption (fileMessageData.caption) if any.
    Voice/audio (typeMessage == audioMessage): is_voice=True, audio_url =
    fileMessageData.downloadUrl, transcription_status='pending'.
    """
    sender = payload.get("senderData", {}) or {}
    data = payload.get("messageData", {}) or {}
    type_message = data.get("typeMessage", "") or ""

    text = None
    is_voice = False
    audio_url = None
    transcription_status = TRANSCRIPTION_NONE

    if type_message == "textMessage":
        text = (data.get("textMessageData", {}) or {}).get("textMessage")
    elif type_message == "extendedTextMessage":
        text = (data.get("extendedTextMessageData", {}) or {}).get("text")
    elif type_message == "audioMessage":
        is_voice = True
        file_data = data.get("fileMessageData", {}) or {}
        audio_url = file_data.get("downloadUrl")
        transcription_status = TRANSCRIPTION_PENDING
    else:
        # image / video / document / etc. — store the type and any caption; no text body.
        file_data = data.get("fileMessageData", {}) or {}
        text = file_data.get("caption") or None

    ts = payload.get("timestamp", 0) or 0
    try:
        timestamp = datetime.fromtimestamp(ts) if ts else None
    except (ValueError, OverflowError, OSError):
        timestamp = None

    return {
        "group_id": sender.get("chatId", ""),
        "group_name": sender.get("chatName", ""),
        "sender": sender.get("sender", ""),
        "sender_name": sender.get("senderName") or sender.get("senderContactName") or "",
        "id_message": payload.get("idMessage", ""),
        "type_message": type_message,
        "text": text,
        "is_voice": is_voice,
        "audio_url": audio_url,
        "transcription_status": transcription_status,
        "timestamp": timestamp,
    }


async def _is_listener_instance(db, instance_id: str) -> bool:
    acc = (await db.execute(
        select(Account).where(Account.instance_id == instance_id)
    )).scalar_one_or_none()
    return bool(acc and getattr(acc, "is_listener", False))


async def _monitored_group(db, instance_id: str, group_id: str) -> MonitoredGroup | None:
    return (await db.execute(
        select(MonitoredGroup).where(
            MonitoredGroup.listener_instance_id == instance_id,
            MonitoredGroup.group_id == group_id,
            MonitoredGroup.is_monitored.is_(True),
        )
    )).scalar_one_or_none()


async def ingest_group_message(instance_id: str, payload: dict, platform: str = "whatsapp"):
    """Capture one incoming group message if (and only if) it belongs to a listener
    instance and a monitored group. Deduped on id_message. Returns the GroupMessage id
    (str) for a new row, or None if ignored/duplicate. Opens its own session; safe to call
    best-effort. In PART 3/4 the caller kicks detection/voice off the returned id.
    Platform-aware: WhatsApp groups end '@g.us', Telegram groups are a negative number.
    """
    sender = payload.get("senderData", {}) or {}
    chat_id = sender.get("chatId", "")
    if not is_group_chat(chat_id, platform):
        return None  # private chat → handled by the existing inbox path, not here

    id_message = payload.get("idMessage", "")
    if not id_message:
        return None

    async with AsyncSessionLocal() as db:
        if not await _is_listener_instance(db, instance_id):
            return None
        mg = await _monitored_group(db, instance_id, chat_id)
        if not mg:
            return None  # group not monitored → ignore

        # Dedupe on Green API idMessage (unique). Green API can deliver the same event twice.
        existing = (await db.execute(
            select(GroupMessage).where(GroupMessage.id_message == id_message)
        )).scalar_one_or_none()
        if existing:
            return None

        fields = extract_group_message_fields(payload)
        # group_name falls back to the monitored-group record if the webhook omitted it.
        gm = GroupMessage(
            listener_instance_id=instance_id,
            platform=platform,
            group_id=fields["group_id"] or chat_id,
            group_name=fields["group_name"] or (mg.group_name or ""),
            sender=fields["sender"],
            sender_name=fields["sender_name"],
            id_message=id_message,
            type_message=fields["type_message"],
            text=fields["text"],
            is_voice=fields["is_voice"],
            audio_url=fields["audio_url"],
            transcription_status=fields["transcription_status"],
            timestamp=fields["timestamp"],
        )
        db.add(gm)
        try:
            await db.commit()
        except Exception as e:
            # A concurrent duplicate delivery lost the race on the unique index — fine.
            await db.rollback()
            logger.debug("group_message insert race (deduped): %s", e)
            return None
        await db.refresh(gm)
        return str(gm.id)
