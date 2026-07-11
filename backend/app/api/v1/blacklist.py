from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.inbox import Blacklist, InboxMessage
from app.models.contact import Contact

router = APIRouter(prefix="/blacklist", tags=["blacklist"])


@router.get("/")
async def list_blacklist(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Blacklist).order_by(Blacklist.created_at.desc()))
    rows = result.scalars().all()
    return [
        {"id": str(b.id), "phone": b.phone, "reason": b.reason, "created_at": str(b.created_at)}
        for b in rows
    ]


@router.post("/")
async def add_to_blacklist(phone: str, reason: str = None, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Blacklist).where(Blacklist.phone == phone))
    if existing.scalar_one_or_none():
        return {"status": "already_blacklisted"}

    db.add(Blacklist(phone=phone, reason=reason))
    contact = await db.execute(select(Contact).where(Contact.phone == phone))
    c = contact.scalar_one_or_none()
    if c:
        c.blacklisted = True
        c.blacklist_reason = reason
    await db.commit()
    return {"status": "blacklisted", "phone": phone}


@router.delete("/{phone}")
async def remove_from_blacklist(phone: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Blacklist).where(Blacklist.phone == phone))
    bl = result.scalar_one_or_none()
    if not bl:
        raise HTTPException(404, "Not in blacklist")

    contact = await db.execute(select(Contact).where(Contact.phone == phone))
    c = contact.scalar_one_or_none()
    if c:
        c.blacklisted = False
        c.blacklist_reason = None

    await db.delete(bl)
    await db.commit()
    return {"success": True}


@router.get("/opt-out-log")
async def opt_out_log(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """V13.4 — recent auto opt-outs (keyword reply / block) + this-week count."""
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from app.models.optout import OptOutLog
    rows = (await db.execute(
        select(OptOutLog).order_by(OptOutLog.created_at.desc()).limit(min(limit, 500))
    )).scalars().all()
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_count = (await db.execute(
        select(func.count()).select_from(OptOutLog).where(OptOutLog.created_at >= week_ago)
    )).scalar() or 0
    return {
        "week_count": week_count,
        "logs": [
            {"id": str(r.id), "phone": r.phone, "reason": r.reason,
             "campaign_id": str(r.campaign_id) if r.campaign_id else None,
             "created_at": str(r.created_at)}
            for r in rows
        ],
    }


@router.get("/inbox/recent")
async def recent_inbox(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Latest incoming messages across all accounts (kept for monitoring widgets)."""
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
            "category": m.category,
            "is_group": m.is_group,
            "received_at": str(m.received_at),
        }
        for m in rows
    ]
