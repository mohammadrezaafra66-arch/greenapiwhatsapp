import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.inbox import InboxMessage
from app.models.account import Account

router = APIRouter(prefix="/inbox", tags=["inbox"])


class ReplyBody(BaseModel):
    message_id: str
    text: str


@router.get("/")
async def list_inbox(
    unread: bool = None,
    category: str = None,
    instance_id: str = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    query = select(InboxMessage)
    if unread is not None:
        # unread=True → only unread; unread=False → only read
        query = query.where(InboxMessage.is_read == (not unread))
    if category:
        query = query.where(InboxMessage.category == category)
    if instance_id:
        query = query.where(InboxMessage.instance_id == instance_id)
    query = query.order_by(InboxMessage.received_at.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "instance_id": m.instance_id,
            "sender_phone": m.sender_phone,
            "sender_name": m.sender_name,
            "text": m.text_content,
            "message_type": m.message_type,
            "category": m.category,
            "is_group": m.is_group,
            "is_read": m.is_read,
            "auto_replied": m.auto_replied,
            "call_status": m.call_status,
            "button_reply_id": m.button_reply_id,
            "button_reply_title": m.button_reply_title,
            "poll_votes": m.poll_votes,
            "received_at": str(m.received_at),
        }
        for m in rows
    ]


@router.post("/{message_id}/read")
async def mark_read(message_id: str, db: AsyncSession = Depends(get_db)):
    msg = await db.get(InboxMessage, uuid.UUID(message_id))
    if not msg:
        raise HTTPException(404, "Message not found")
    msg.is_read = True
    await db.commit()

    # Best-effort: also mark the real WhatsApp chat as read via Green API.
    try:
        acc_result = await db.execute(select(Account).where(Account.instance_id == msg.instance_id))
        account = acc_result.scalar_one_or_none()
        if account:
            import json
            from app.services.green_api import GreenAPIClient
            green_id = ""
            if msg.original_payload:
                try:
                    green_id = json.loads(msg.original_payload).get("idMessage", "") or ""
                except Exception:
                    green_id = ""
            client = GreenAPIClient(account.instance_id, account.api_token)
            await client.mark_as_read(msg.sender_phone, green_id)
    except Exception as e:
        print(f"[Inbox] readChat sync failed (non-fatal): {e}")

    return {"success": True}


@router.post("/reply")
async def reply_to_message(body: ReplyBody, db: AsyncSession = Depends(get_db)):
    msg = await db.get(InboxMessage, uuid.UUID(body.message_id))
    if not msg:
        raise HTTPException(404, "Message not found")

    acc_result = await db.execute(select(Account).where(Account.instance_id == msg.instance_id))
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(400, "Account for this message not found")

    from app.services.green_api import GreenAPIClient
    client = GreenAPIClient(account.instance_id, account.api_token)
    sent_id = await client.send_message(msg.sender_phone, body.text)
    msg.is_read = True
    await db.commit()
    return {"sent": bool(sent_id), "message_id": sent_id}


@router.get("/stats")
async def inbox_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InboxMessage.category, func.count()).group_by(InboxMessage.category)
    )
    by_category = {row[0] or "uncategorized": row[1] for row in result.all()}

    unread_result = await db.execute(
        select(func.count()).where(InboxMessage.is_read == False)
    )
    unread = unread_result.scalar()
    return {"by_category": by_category, "unread": unread}
