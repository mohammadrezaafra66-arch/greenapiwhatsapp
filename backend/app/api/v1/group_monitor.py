"""V26 — group-monitoring API (listener designation, monitored groups, keywords,
messages, admin alerts). Grown across PART 1 (listener) and PART 5 (UI endpoints)."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.account import Account
from app.models.group_monitor import (
    MonitoredGroup, GroupMessage, GroupKeyword, GroupPredefinedReply, GroupForbiddenAlert,
    CONVERSATION_MODES, KEYWORD_KINDS, CONVERSATION_MODE_OFF,
)

router = APIRouter(prefix="/group-monitor", tags=["group-monitor"])


# ── PART 1 — listener designation ────────────────────────────────────────────
class ListenerBody(BaseModel):
    is_listener: bool = True


@router.post("/listener/{account_id}")
async def set_listener_role(account_id: str, body: ListenerBody, db: AsyncSession = Depends(get_db)):
    """Designate (or clear) an account as a dedicated group-monitoring listener.
    Enforces the one-account-one-role guard (mutually exclusive with warm-up/campaign)."""
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    from app.services.listener_service import set_listener
    ok, err = await set_listener(db, acc, body.is_listener)
    if not ok:
        raise HTTPException(400, err)
    await db.commit()

    webhook_applied = False
    if acc.is_listener:
        # Enable the incomingWebhook setting so group messages reach the backend. This is
        # webhook-only: polling is NEVER touched and the webhook URL / ngrok is NOT changed.
        try:
            from app.services.green_api import GreenAPIClient
            client = GreenAPIClient(acc.instance_id, acc.api_token)
            webhook_applied = await client.set_settings({"incomingWebhook": "yes"})
        except Exception:
            webhook_applied = False
    return {"account_id": account_id, "is_listener": acc.is_listener,
            "incoming_webhook_applied": bool(webhook_applied)}


@router.get("/listeners")
async def list_listeners(db: AsyncSession = Depends(get_db)):
    """All accounts currently marked as listeners."""
    accs = (await db.execute(select(Account).where(Account.is_listener.is_(True)))).scalars().all()
    return [{"id": str(a.id), "name": a.name, "instance_id": a.instance_id, "phone": a.phone}
            for a in accs]


# ── PART 5 — monitored groups ────────────────────────────────────────────────
def merge_groups_with_monitored(wa_groups: list, monitored_rows: list) -> list:
    """Pure: annotate the listener's WhatsApp groups (from getContacts?group=true) with their
    monitored_group state. `wa_groups` items are {id, name}; `monitored_rows` are
    MonitoredGroup objects. Groups already monitored are marked; the rest default to off."""
    by_id = {m.group_id: m for m in monitored_rows}
    out = []
    for g in wa_groups:
        gid = g.get("id") or g.get("chatId") or ""
        m = by_id.get(gid)
        out.append({
            "group_id": gid,
            "group_name": g.get("name") or g.get("subject") or (m.group_name if m else ""),
            "is_monitored": bool(m.is_monitored) if m else False,
            "auto_reply_enabled": bool(m.auto_reply_enabled) if m else False,
            "conversation_mode": m.conversation_mode if m else CONVERSATION_MODE_OFF,
            "monitored_id": str(m.id) if m else None,
        })
    return out


@router.get("/available-groups/{account_id}")
async def available_groups(account_id: str, db: AsyncSession = Depends(get_db)):
    """List the listener account's WhatsApp groups (getContacts?group=true), each annotated
    with its monitored state so the UI can toggle monitoring per group."""
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    if not acc.is_listener:
        raise HTTPException(400, "این حساب شنونده نیست؛ ابتدا آن را به‌عنوان شنونده تعیین کنید.")
    wa_groups = []
    try:
        from app.services.green_api import GreenAPIClient
        contacts = await GreenAPIClient(acc.instance_id, acc.api_token).get_group_contacts()
        for c in contacts or []:
            wa_groups.append({"id": c.get("id") or c.get("chatId"),
                              "name": c.get("name") or c.get("contactName") or ""})
    except Exception:
        wa_groups = []
    monitored = (await db.execute(
        select(MonitoredGroup).where(MonitoredGroup.listener_instance_id == acc.instance_id)
    )).scalars().all()
    return merge_groups_with_monitored(wa_groups, monitored)


class MonitoredUpsert(BaseModel):
    listener_instance_id: str
    group_id: str
    group_name: str | None = None
    is_monitored: bool = True
    auto_reply_enabled: bool = False
    conversation_mode: str = CONVERSATION_MODE_OFF
    platform: str = "whatsapp"    # TG — 'whatsapp' | 'telegram'


@router.get("/monitored")
async def list_monitored(listener_instance_id: str | None = None,
                         db: AsyncSession = Depends(get_db)):
    q = select(MonitoredGroup)
    if listener_instance_id:
        q = q.where(MonitoredGroup.listener_instance_id == listener_instance_id)
    rows = (await db.execute(q.order_by(MonitoredGroup.created_at.desc()))).scalars().all()
    return [_monitored_dict(m) for m in rows]


@router.post("/monitored")
async def upsert_monitored(body: MonitoredUpsert, db: AsyncSession = Depends(get_db)):
    """Mark a group monitored (or update its config). Upsert on (listener_instance_id, group_id)."""
    if body.conversation_mode not in CONVERSATION_MODES:
        raise HTTPException(400, "حالت گفتگو نامعتبر است")
    existing = (await db.execute(
        select(MonitoredGroup).where(
            MonitoredGroup.listener_instance_id == body.listener_instance_id,
            MonitoredGroup.group_id == body.group_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.group_name = body.group_name if body.group_name is not None else existing.group_name
        existing.is_monitored = body.is_monitored
        existing.auto_reply_enabled = body.auto_reply_enabled
        existing.conversation_mode = body.conversation_mode
        m = existing
    else:
        from app.services.platforms import normalize_platform
        m = MonitoredGroup(
            listener_instance_id=body.listener_instance_id, group_id=body.group_id,
            group_name=body.group_name, is_monitored=body.is_monitored,
            auto_reply_enabled=body.auto_reply_enabled, conversation_mode=body.conversation_mode,
            platform=normalize_platform(body.platform),
        )
        db.add(m)
    await db.commit()
    await db.refresh(m)
    return _monitored_dict(m)


class MonitoredPatch(BaseModel):
    is_monitored: bool | None = None
    auto_reply_enabled: bool | None = None
    conversation_mode: str | None = None


@router.patch("/monitored/{monitored_id}")
async def patch_monitored(monitored_id: str, body: MonitoredPatch,
                          db: AsyncSession = Depends(get_db)):
    m = await db.get(MonitoredGroup, uuid.UUID(monitored_id))
    if not m:
        raise HTTPException(404, "گروه یافت نشد")
    if body.conversation_mode is not None:
        if body.conversation_mode not in CONVERSATION_MODES:
            raise HTTPException(400, "حالت گفتگو نامعتبر است")
        m.conversation_mode = body.conversation_mode
    if body.is_monitored is not None:
        m.is_monitored = body.is_monitored
    if body.auto_reply_enabled is not None:
        m.auto_reply_enabled = body.auto_reply_enabled
    await db.commit()
    return _monitored_dict(m)


@router.delete("/monitored/{monitored_id}")
async def delete_monitored(monitored_id: str, db: AsyncSession = Depends(get_db)):
    m = await db.get(MonitoredGroup, uuid.UUID(monitored_id))
    if not m:
        raise HTTPException(404, "گروه یافت نشد")
    await db.delete(m)
    await db.commit()
    return {"deleted": True}


def _monitored_dict(m: MonitoredGroup) -> dict:
    return {
        "id": str(m.id), "listener_instance_id": m.listener_instance_id,
        "group_id": m.group_id, "group_name": m.group_name,
        "is_monitored": bool(m.is_monitored), "auto_reply_enabled": bool(m.auto_reply_enabled),
        "conversation_mode": m.conversation_mode,
    }


# ── PART 5 — keyword manager ─────────────────────────────────────────────────
class KeywordBody(BaseModel):
    word: str
    kind: str = "trigger"   # trigger | forbidden
    active: bool = True


@router.get("/keywords")
async def list_keywords(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(GroupKeyword).order_by(GroupKeyword.created_at))).scalars().all()
    return [{"id": str(k.id), "word": k.word, "kind": k.kind, "active": bool(k.active)}
            for k in rows]


@router.post("/keywords")
async def create_keyword(body: KeywordBody, db: AsyncSession = Depends(get_db)):
    if body.kind not in KEYWORD_KINDS:
        raise HTTPException(400, "نوع کلمه کلیدی نامعتبر است")
    if not body.word.strip():
        raise HTTPException(400, "کلمه کلیدی نمی‌تواند خالی باشد")
    k = GroupKeyword(word=body.word.strip(), kind=body.kind, active=body.active)
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return {"id": str(k.id), "word": k.word, "kind": k.kind, "active": bool(k.active)}


@router.put("/keywords/{keyword_id}")
async def update_keyword(keyword_id: str, body: KeywordBody, db: AsyncSession = Depends(get_db)):
    k = await db.get(GroupKeyword, uuid.UUID(keyword_id))
    if not k:
        raise HTTPException(404, "کلمه کلیدی یافت نشد")
    if body.kind not in KEYWORD_KINDS:
        raise HTTPException(400, "نوع کلمه کلیدی نامعتبر است")
    k.word = body.word.strip()
    k.kind = body.kind
    k.active = body.active
    await db.commit()
    return {"id": keyword_id, "updated": True}


@router.delete("/keywords/{keyword_id}")
async def delete_keyword(keyword_id: str, db: AsyncSession = Depends(get_db)):
    k = await db.get(GroupKeyword, uuid.UUID(keyword_id))
    if not k:
        raise HTTPException(404, "کلمه کلیدی یافت نشد")
    await db.delete(k)
    await db.commit()
    return {"deleted": True}


# ── PART 5 — predefined replies ──────────────────────────────────────────────
class ReplyBody(BaseModel):
    reply_text: str
    keyword_id: str | None = None
    active: bool = True


@router.get("/replies")
async def list_replies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(GroupPredefinedReply).order_by(GroupPredefinedReply.created_at))).scalars().all()
    return [{"id": str(r.id), "reply_text": r.reply_text,
             "keyword_id": str(r.keyword_id) if r.keyword_id else None,
             "active": bool(r.active)} for r in rows]


@router.post("/replies")
async def create_reply(body: ReplyBody, db: AsyncSession = Depends(get_db)):
    if not body.reply_text.strip():
        raise HTTPException(400, "متن پاسخ نمی‌تواند خالی باشد")
    r = GroupPredefinedReply(
        reply_text=body.reply_text.strip(),
        keyword_id=uuid.UUID(body.keyword_id) if body.keyword_id else None,
        active=body.active,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"id": str(r.id)}


@router.put("/replies/{reply_id}")
async def update_reply(reply_id: str, body: ReplyBody, db: AsyncSession = Depends(get_db)):
    r = await db.get(GroupPredefinedReply, uuid.UUID(reply_id))
    if not r:
        raise HTTPException(404, "پاسخ یافت نشد")
    r.reply_text = body.reply_text.strip()
    r.keyword_id = uuid.UUID(body.keyword_id) if body.keyword_id else None
    r.active = body.active
    await db.commit()
    return {"id": reply_id, "updated": True}


@router.delete("/replies/{reply_id}")
async def delete_reply(reply_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.get(GroupPredefinedReply, uuid.UUID(reply_id))
    if not r:
        raise HTTPException(404, "پاسخ یافت نشد")
    await db.delete(r)
    await db.commit()
    return {"deleted": True}


# ── PART 5 — captured group messages ─────────────────────────────────────────
@router.get("/messages")
async def list_messages(group_id: str | None = None, listener_instance_id: str | None = None,
                        limit: int = 200, db: AsyncSession = Depends(get_db)):
    q = select(GroupMessage)
    if group_id:
        q = q.where(GroupMessage.group_id == group_id)
    if listener_instance_id:
        q = q.where(GroupMessage.listener_instance_id == listener_instance_id)
    rows = (await db.execute(
        q.order_by(GroupMessage.created_at.desc()).limit(min(limit, 500)))).scalars().all()
    return [{
        "id": str(m.id), "group_id": m.group_id, "group_name": m.group_name,
        "sender": m.sender, "sender_name": m.sender_name,
        "type_message": m.type_message, "text": m.text, "is_voice": bool(m.is_voice),
        "transcription": m.transcription, "transcription_status": m.transcription_status,
        "matched_keywords": m.matched_keywords, "flagged_forbidden": bool(m.flagged_forbidden),
        "replied": bool(m.replied),
        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in rows]


# ── PART 5 — admin forbidden-word alerts ─────────────────────────────────────
@router.get("/alerts")
async def list_alerts(only_unread: bool = False, limit: int = 200,
                      db: AsyncSession = Depends(get_db)):
    q = select(GroupForbiddenAlert)
    if only_unread:
        q = q.where(GroupForbiddenAlert.is_read.is_(False))
    rows = (await db.execute(
        q.order_by(GroupForbiddenAlert.created_at.desc()).limit(min(limit, 500)))).scalars().all()
    return [{
        "id": str(a.id), "group_id": a.group_id, "group_name": a.group_name,
        "sender": a.sender, "sender_name": a.sender_name, "word": a.word,
        "message_text": a.message_text, "is_read": bool(a.is_read),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in rows]


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str, db: AsyncSession = Depends(get_db)):
    a = await db.get(GroupForbiddenAlert, uuid.UUID(alert_id))
    if not a:
        raise HTTPException(404, "هشدار یافت نشد")
    a.is_read = True
    await db.commit()
    return {"id": alert_id, "is_read": True}
