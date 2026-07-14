"""V14 PART B — messaging endpoints (Features 12/13/14) + content management.

Send a contact card, a location, or forward messages; CRUD for saved contact cards,
saved locations, and button auto-replies; read button-reply stats and reactions.

Note: sendReaction is NOT exposed — the PHASE 0 probe returned 403 (plan-restricted),
so per FEATURE 11 we ship receive-only reactions and no send-reaction endpoint.
"""
import re
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.campaign import CampaignContact
from app.models.messaging import (
    ButtonReply, ButtonAutoReply, MessageReaction, SavedContactCard, SavedLocation,
)
from app.services.green_api import GreenAPIClient
from app.services.interactive import validate_buttons
from app.models.inbox import InboxMessage
from app.models.wa_extras import DisappearingChatSetting
from app.services.msgcontrol import edit_window_ok, valid_disappearing, DISAPPEARING_VALUES
from app.utils.shamsi import to_shamsi

logger = logging.getLogger("afrakala.messages")
router = APIRouter(prefix="/messages", tags=["messages"])


async def _account(db: AsyncSession, account_id: str | None) -> Account:
    """Resolve the sending account: the given id, else the default, else any active."""
    if account_id:
        acc = await db.get(Account, uuid.UUID(account_id))
        if not acc:
            raise HTTPException(404, "حساب یافت نشد")
        return acc
    acc = (await db.execute(
        select(Account).where(Account.is_default.is_(True), Account.status == AccountStatus.active)
    )).scalars().first()
    if not acc:
        acc = (await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )).scalars().first()
    if not acc:
        raise HTTPException(400, "هیچ حساب متصلی برای ارسال وجود ندارد")
    return acc


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


# ── FEATURE 12 — send contact card ──────────────────────────────────────────
class ContactBody(BaseModel):
    account_id: str | None = None
    chat_id: str                      # phone or full chatId
    saved_card_id: str | None = None
    phone_contact: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    company: str | None = "افراکالا"


@router.post("/contact")
async def send_contact(body: ContactBody, db: AsyncSession = Depends(get_db)):
    acc = await _account(db, body.account_id)
    if body.saved_card_id:
        card = await db.get(SavedContactCard, uuid.UUID(body.saved_card_id))
        if not card:
            raise HTTPException(404, "کارت ذخیره‌شده یافت نشد")
        contact = {
            "phoneContact": int(_digits(card.phone_contact)),
            "firstName": card.first_name or "",
            "lastName": card.last_name or "",
            "company": card.company or "",
        }
    else:
        pc = _digits(body.phone_contact)
        if not pc:
            raise HTTPException(400, "شماره مخاطب لازم است")
        contact = {
            "phoneContact": int(pc),
            "firstName": body.first_name or "",
            "middleName": body.middle_name or "",
            "lastName": body.last_name or "",
            "company": body.company or "",
        }
    try:
        msg_id = await GreenAPIClient(acc.instance_id, acc.api_token).send_contact_card(body.chat_id, contact)
    except Exception as e:
        logger.error("sendContact failed: %s", e)
        raise HTTPException(502, "ارسال کارت مخاطب ناموفق بود")
    return {"idMessage": msg_id}


# ── FEATURE 13 — send location ──────────────────────────────────────────────
class LocationBody(BaseModel):
    account_id: str | None = None
    chat_id: str
    saved_location_id: str | None = None
    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@router.post("/location")
async def send_location(body: LocationBody, db: AsyncSession = Depends(get_db)):
    acc = await _account(db, body.account_id)
    if body.saved_location_id:
        loc = await db.get(SavedLocation, uuid.UUID(body.saved_location_id))
        if not loc:
            raise HTTPException(404, "موقعیت ذخیره‌شده یافت نشد")
        name, address, lat, lon = loc.name, loc.address, loc.latitude, loc.longitude
    else:
        if body.latitude is None or body.longitude is None:
            raise HTTPException(400, "طول و عرض جغرافیایی لازم است")
        name, address, lat, lon = body.name or "", body.address or "", body.latitude, body.longitude
    try:
        msg_id = await GreenAPIClient(acc.instance_id, acc.api_token).send_location_full(
            body.chat_id, name, address, lat, lon)
    except Exception as e:
        logger.error("sendLocation failed: %s", e)
        raise HTTPException(502, "ارسال موقعیت ناموفق بود")
    return {"idMessage": msg_id}


# ── FEATURE 14 — forward messages ───────────────────────────────────────────
class ForwardBody(BaseModel):
    account_id: str | None = None
    chat_id: str                       # destination
    chat_id_from: str                  # source chat
    message_ids: list[str]


@router.post("/forward")
async def forward_messages(body: ForwardBody, db: AsyncSession = Depends(get_db)):
    if not body.message_ids:
        raise HTTPException(400, "حداقل یک پیام برای فوروارد لازم است")
    acc = await _account(db, body.account_id)
    try:
        msg_id = await GreenAPIClient(acc.instance_id, acc.api_token).forward_to(
            body.chat_id, body.chat_id_from, body.message_ids)
    except Exception as e:
        logger.error("forwardMessages failed: %s", e)
        raise HTTPException(502, "فوروارد ناموفق بود")
    return {"idMessage": msg_id}


# ── Saved contact cards (CRUD) ──────────────────────────────────────────────
class SavedCardBody(BaseModel):
    label: str
    phone_contact: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = "افراکالا"
    is_default: bool = False


@router.get("/saved-contacts")
async def list_saved_contacts(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SavedContactCard).order_by(SavedContactCard.created_at.desc()))).scalars().all()
    return [{"id": str(c.id), "label": c.label, "phone_contact": c.phone_contact,
             "first_name": c.first_name, "last_name": c.last_name, "company": c.company,
             "is_default": c.is_default} for c in rows]


@router.post("/saved-contacts")
async def create_saved_contact(body: SavedCardBody, db: AsyncSession = Depends(get_db)):
    card = SavedContactCard(label=body.label, phone_contact=_digits(body.phone_contact),
                            first_name=body.first_name, last_name=body.last_name,
                            company=body.company, is_default=body.is_default)
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return {"id": str(card.id)}


@router.delete("/saved-contacts/{card_id}")
async def delete_saved_contact(card_id: str, db: AsyncSession = Depends(get_db)):
    card = await db.get(SavedContactCard, uuid.UUID(card_id))
    if card:
        await db.delete(card)
        await db.commit()
    return {"ok": True}


# ── Saved locations (CRUD) ──────────────────────────────────────────────────
class SavedLocationBody(BaseModel):
    name: str
    address: str | None = None
    latitude: float
    longitude: float
    is_default: bool = False


@router.get("/saved-locations")
async def list_saved_locations(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SavedLocation).order_by(SavedLocation.created_at.desc()))).scalars().all()
    return [{"id": str(l.id), "name": l.name, "address": l.address, "latitude": l.latitude,
             "longitude": l.longitude, "is_default": l.is_default} for l in rows]


@router.post("/saved-locations")
async def create_saved_location(body: SavedLocationBody, db: AsyncSession = Depends(get_db)):
    loc = SavedLocation(name=body.name, address=body.address, latitude=body.latitude,
                        longitude=body.longitude, is_default=body.is_default)
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return {"id": str(loc.id)}


@router.delete("/saved-locations/{loc_id}")
async def delete_saved_location(loc_id: str, db: AsyncSession = Depends(get_db)):
    loc = await db.get(SavedLocation, uuid.UUID(loc_id))
    if loc:
        await db.delete(loc)
        await db.commit()
    return {"ok": True}


# ── Button auto-replies (CRUD) — FEATURE 8 ──────────────────────────────────
class AutoReplyBody(BaseModel):
    button_id: str | None = None
    button_text: str | None = None
    reply_text: str
    enabled: bool = True


@router.get("/button-auto-replies")
async def list_auto_replies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ButtonAutoReply).order_by(ButtonAutoReply.created_at.desc()))).scalars().all()
    return [{"id": str(r.id), "button_id": r.button_id, "button_text": r.button_text,
             "reply_text": r.reply_text, "enabled": r.enabled} for r in rows]


@router.post("/button-auto-replies")
async def create_auto_reply(body: AutoReplyBody, db: AsyncSession = Depends(get_db)):
    if not (body.button_id or body.button_text):
        raise HTTPException(400, "شناسه دکمه یا متن دکمه لازم است")
    rule = ButtonAutoReply(button_id=body.button_id, button_text=body.button_text,
                           reply_text=body.reply_text, enabled=body.enabled)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {"id": str(rule.id)}


@router.put("/button-auto-replies/{rule_id}")
async def update_auto_reply(rule_id: str, body: AutoReplyBody, db: AsyncSession = Depends(get_db)):
    rule = await db.get(ButtonAutoReply, uuid.UUID(rule_id))
    if not rule:
        raise HTTPException(404, "قانون یافت نشد")
    rule.button_id = body.button_id
    rule.button_text = body.button_text
    rule.reply_text = body.reply_text
    rule.enabled = body.enabled
    await db.commit()
    return {"ok": True}


@router.delete("/button-auto-replies/{rule_id}")
async def delete_auto_reply(rule_id: str, db: AsyncSession = Depends(get_db)):
    rule = await db.get(ButtonAutoReply, uuid.UUID(rule_id))
    if rule:
        await db.delete(rule)
        await db.commit()
    return {"ok": True}


# ── Validate a button config (used by the campaign UI before save) ──────────
class ValidateButtonsBody(BaseModel):
    buttons: list[dict]


@router.post("/validate-buttons")
async def validate_buttons_endpoint(body: ValidateButtonsBody):
    try:
        validate_buttons(body.buttons)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ── Button-reply stats for a campaign — FEATURE 8 panel ─────────────────────
@router.get("/campaign/{campaign_id}/button-replies")
async def campaign_button_replies(campaign_id: str, db: AsyncSession = Depends(get_db)):
    cid = uuid.UUID(campaign_id)
    counts = (await db.execute(
        select(ButtonReply.button_id, ButtonReply.button_text, func.count().label("n"))
        .where(ButtonReply.campaign_id == cid)
        .group_by(ButtonReply.button_id, ButtonReply.button_text)
    )).all()
    rows = (await db.execute(
        select(ButtonReply).where(ButtonReply.campaign_id == cid)
        .order_by(ButtonReply.created_at.desc()).limit(500)
    )).scalars().all()
    return {
        "counts": [{"button_id": b, "button_text": t, "count": n} for b, t, n in counts],
        "presses": [{"phone": r.contact_phone, "button_id": r.button_id,
                     "button_text": r.button_text, "at": to_shamsi(r.created_at)} for r in rows],
    }


# ── FEATURE 9 — edit a sent message (15-min window, silent-failure aware) ───
class EditBody(BaseModel):
    account_id: str | None = None
    chat_id: str
    message_id: str
    message: str


@router.post("/edit")
async def edit_message(body: EditBody, db: AsyncSession = Depends(get_db)):
    acc = await _account(db, body.account_id)
    # Server-side 15-minute re-check when we know when the message was sent.
    cc = (await db.execute(
        select(CampaignContact).where(CampaignContact.green_api_message_id == body.message_id)
    )).scalar_one_or_none()
    if cc is not None and not edit_window_ok(cc.sent_at):
        raise HTTPException(400, "مهلت ۱۵ دقیقه‌ای ویرایش این پیام تمام شده است")
    try:
        # ⚠️ HTTP 200 even on silent failure — the editedMessage/outgoingMessageStatus
        # webhooks confirm/deny; we optimistically update local state.
        await GreenAPIClient(acc.instance_id, acc.api_token).edit_message_raw(
            body.chat_id, body.message_id, body.message)
    except Exception as e:
        logger.error("editMessage failed: %s", e)
        raise HTTPException(502, "ویرایش پیام ناموفق بود")
    if cc is not None:
        cc.generated_message = body.message
        await db.commit()
    return {"ok": True, "note": "ویرایش ارسال شد؛ در صورت گذشتن مهلت، واتساپ آن را اعمال نمی‌کند"}


# ── FEATURE 10 — delete a sent message (for everyone / only me) ──────────────
class DeleteBody(BaseModel):
    account_id: str | None = None
    chat_id: str
    message_id: str
    only_sender: bool = False


@router.post("/delete")
async def delete_message(body: DeleteBody, db: AsyncSession = Depends(get_db)):
    acc = await _account(db, body.account_id)
    try:
        await GreenAPIClient(acc.instance_id, acc.api_token).delete_message_raw(
            body.chat_id, body.message_id, only_sender=body.only_sender)
    except Exception as e:
        logger.error("deleteMessage failed: %s", e)
        raise HTTPException(502, "حذف پیام ناموفق بود")
    return {"ok": True}


# ── FEATURE 21 — mark chat(s) as read ───────────────────────────────────────
class ReadBody(BaseModel):
    account_id: str | None = None
    chat_id: str
    message_id: str | None = None


@router.post("/read")
async def read_chat(body: ReadBody, db: AsyncSession = Depends(get_db)):
    acc = await _account(db, body.account_id)
    try:
        await GreenAPIClient(acc.instance_id, acc.api_token).read_chat(body.chat_id, body.message_id)
    except Exception as e:
        logger.error("readChat failed: %s", e)
        raise HTTPException(502, "علامت‌گذاری خوانده‌شده ناموفق بود")
    return {"ok": True}


class ReadAllBody(BaseModel):
    account_id: str | None = None
    chat_ids: list[str]


@router.post("/read-all")
async def read_all(body: ReadAllBody, db: AsyncSession = Depends(get_db)):
    acc = await _account(db, body.account_id)
    client = GreenAPIClient(acc.instance_id, acc.api_token)
    done = 0
    for chat in body.chat_ids[:500]:
        try:
            await client.read_chat(chat)
            done += 1
        except Exception:
            continue
    return {"ok": True, "marked": done}


# ── FEATURE 15 — archive / unarchive a chat ─────────────────────────────────
class ArchiveBody(BaseModel):
    account_id: str | None = None
    chat_id: str
    archived: bool = True


@router.post("/archive")
async def archive_chat(body: ArchiveBody, db: AsyncSession = Depends(get_db)):
    acc = await _account(db, body.account_id)
    client = GreenAPIClient(acc.instance_id, acc.api_token)
    try:
        if body.archived:
            await client.archive_chat_raw(body.chat_id)
        else:
            await client.unarchive_chat_raw(body.chat_id)
    except Exception as e:
        logger.error("archiveChat failed: %s", e)
        raise HTTPException(502, "آرشیو/بازگردانی چت ناموفق بود")
    # Reflect locally so the Inbox updates instantly (match by bare phone).
    phone = _digits(body.chat_id.split("@")[0])
    await db.execute(
        text("UPDATE inbox_messages SET archived = :a WHERE sender_phone = :p"),
        {"a": body.archived, "p": phone},
    )
    await db.commit()
    return {"ok": True, "archived": body.archived}


# ── FEATURE 16 — disappearing messages ──────────────────────────────────────
class DisappearingBody(BaseModel):
    account_id: str | None = None
    chat_id: str
    ephemeral: int


@router.post("/disappearing")
async def set_disappearing(body: DisappearingBody, db: AsyncSession = Depends(get_db)):
    if not valid_disappearing(body.ephemeral):
        raise HTTPException(400, f"مقدار نامعتبر — فقط {sorted(DISAPPEARING_VALUES)} مجاز است")
    acc = await _account(db, body.account_id)
    try:
        await GreenAPIClient(acc.instance_id, acc.api_token).set_disappearing_raw(body.chat_id, body.ephemeral)
    except Exception as e:
        logger.error("setDisappearingChat failed: %s", e)
        raise HTTPException(502, "تنظیم پیام ناپدیدشونده ناموفق بود")
    # Upsert the local record (unique on account_id + chat_id).
    existing = (await db.execute(
        select(DisappearingChatSetting).where(
            DisappearingChatSetting.account_id == acc.id,
            DisappearingChatSetting.chat_id == body.chat_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.ephemeral = body.ephemeral
    else:
        db.add(DisappearingChatSetting(account_id=acc.id, chat_id=body.chat_id, ephemeral=body.ephemeral))
    await db.commit()
    return {"ok": True, "ephemeral": body.ephemeral}


# ── Recent reactions — FEATURE 11 (receive) ─────────────────────────────────
@router.get("/reactions")
async def list_reactions(chat_id: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(MessageReaction).order_by(MessageReaction.created_at.desc()).limit(200)
    if chat_id:
        q = select(MessageReaction).where(MessageReaction.chat_id == chat_id) \
            .order_by(MessageReaction.created_at.desc()).limit(200)
    rows = (await db.execute(q)).scalars().all()
    return [{"chat_id": r.chat_id, "sender_phone": r.sender_phone, "sender_name": r.sender_name,
             "emoji": r.emoji, "reacted_message_id": r.reacted_message_id,
             "at": to_shamsi(r.created_at)} for r in rows]
