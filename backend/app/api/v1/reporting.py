import uuid
from datetime import date as date_type, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database import get_db
from app.models.reporting import (
    EmergencyContact, ReportSubscriber, DailySendLog, ProductMentionLog,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])


class EmergencyBody(BaseModel):
    name: str | None = None
    phone: str
    purpose: str = "alert"
    is_active: bool = True


class SubscriberBody(BaseModel):
    phone: str
    name: str | None = None
    is_active: bool = True


# ── Emergency contacts ─────────────────────────────────────
@router.get("/emergency-contacts")
async def list_emergency(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EmergencyContact).order_by(EmergencyContact.created_at.desc()))).scalars().all()
    return [
        {"id": str(r.id), "name": r.name, "phone": r.phone, "purpose": r.purpose, "is_active": r.is_active}
        for r in rows
    ]


@router.post("/emergency-contacts")
async def add_emergency(body: EmergencyBody, db: AsyncSession = Depends(get_db)):
    r = EmergencyContact(name=body.name, phone=body.phone, purpose=body.purpose, is_active=body.is_active)
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"id": str(r.id)}


@router.delete("/emergency-contacts/{contact_id}")
async def delete_emergency(contact_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.get(EmergencyContact, uuid.UUID(contact_id))
    if not r:
        raise HTTPException(404, "Not found")
    await db.delete(r)
    await db.commit()
    return {"deleted": True}


# ── Report subscribers ─────────────────────────────────────
@router.get("/subscribers")
async def list_subscribers(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ReportSubscriber).order_by(ReportSubscriber.created_at.desc()))).scalars().all()
    return [
        {"id": str(r.id), "phone": r.phone, "name": r.name, "is_active": r.is_active}
        for r in rows
    ]


@router.post("/subscribers")
async def add_subscriber(body: SubscriberBody, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(ReportSubscriber).where(ReportSubscriber.phone == body.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "این شماره قبلاً ثبت شده است")
    r = ReportSubscriber(phone=body.phone, name=body.name, is_active=body.is_active)
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"id": str(r.id)}


@router.delete("/subscribers/{subscriber_id}")
async def delete_subscriber(subscriber_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.get(ReportSubscriber, uuid.UUID(subscriber_id))
    if not r:
        raise HTTPException(404, "Not found")
    await db.delete(r)
    await db.commit()
    return {"deleted": True}


# ── Daily send logs ────────────────────────────────────────
@router.get("/daily-logs")
async def daily_logs(date: str | None = None, db: AsyncSession = Depends(get_db)):
    query = select(DailySendLog).order_by(DailySendLog.sent_at.desc())
    if date:
        try:
            d = date_type.fromisoformat(date)
            query = query.where(DailySendLog.date == d)
        except ValueError:
            raise HTTPException(400, "Invalid date (use YYYY-MM-DD)")
    query = query.limit(500)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": str(r.id),
            "account_name": r.account_name,
            "campaign_name": r.campaign_name,
            "recipient_phone": r.recipient_phone,
            "recipient_name": r.recipient_name,
            "status": r.status,
            "sent_at": str(r.sent_at),
        }
        for r in rows
    ]


# ── Product mentions ───────────────────────────────────────
@router.get("/product-mentions")
async def product_mentions(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ProductMentionLog).order_by(ProductMentionLog.mentioned_at.desc()).limit(limit)
    )).scalars().all()
    return [
        {"id": str(i.id), "product": i.product_name, "sender": i.sender_phone,
         "sender_name": i.sender_name, "group": i.group_name,
         "time": str(i.mentioned_at), "text": i.message_text}
        for i in rows
    ]


@router.delete("/product-mentions")
async def clear_product_mentions(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(ProductMentionLog))
    await db.commit()
    return {"cleared": True}


# ── Products (for the Products page) ───────────────────────
@router.get("/products")
async def list_products():
    from app.services.price_service import get_products
    return await get_products(200)


# ── Product labels (self-hosted Supabase) ──────────────────
@router.get("/product-labels")
async def get_product_labels():
    """Fetch all active product labels from self-hosted Supabase."""
    import httpx
    from app.config import settings
    url = f"{settings.supabase_url}/rest/v1/product_labels?is_active=eq.true&select=id,title,color"
    headers = {"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {settings.supabase_anon_key}"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, headers=headers)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"[Reporting] product-labels fetch failed: {e}")
    return []
