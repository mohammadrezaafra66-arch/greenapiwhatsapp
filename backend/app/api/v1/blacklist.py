from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.inbox import Blacklist, InboxMessage
from app.models.contact import Contact
import uuid

router = APIRouter(prefix="/blacklist", tags=["blacklist"])


@router.get("/")
async def list_blacklist(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Blacklist).order_by(Blacklist.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "phone": b.phone,
            "reason": b.reason,
            "created_at": str(b.created_at),
        }
        for b in rows
    ]


@router.post("/")
async def add_to_blacklist(phone: str, reason: str = None, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Blacklist).where(Blacklist.phone == phone))
    if existing.scalar_one_or_none():
        return {"status": "already_blacklisted"}

    bl = Blacklist(phone=phone, reason=reason)
    db.add(bl)

    contact = await db.execute(select(Contact).where(Contact.phone == phone))
    c = contact.scalar_one_or_none()
    if c:
        c.blacklisted = True
        c.blacklist_reason = reason

    await db.commit()
    return {"status": "blacklisted", "phone": phone}


@router.delete("/{blacklist_id}")
async def remove_from_blacklist(blacklist_id: str, db: AsyncSession = Depends(get_db)):
    bl = await db.get(Blacklist, uuid.UUID(blacklist_id))
    if not bl:
        raise HTTPException(404, "Blacklist entry not found")

    # Unmark contact
    contact = await db.execute(select(Contact).where(Contact.phone == bl.phone))
    c = contact.scalar_one_or_none()
    if c:
        c.blacklisted = False
        c.blacklist_reason = None

    await db.delete(bl)
    await db.commit()
    return {"success": True}


@router.get("/inbox/recent")
async def recent_inbox(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Latest incoming messages across all accounts."""
    result = await db.execute(
        select(InboxMessage).order_by(InboxMessage.received_at.desc()).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "instance_id": m.instance_id,
            "sender_phone": m.sender_phone,
            "sender_name": m.sender_name,
            "text": m.text_content,
            "is_group": m.is_group,
            "received_at": str(m.received_at),
        }
        for m in rows
    ]
