import uuid
from datetime import date as date_type, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
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
    from app.services.phone_extract import contacts_for
    rows = (await db.execute(
        select(ProductMentionLog).order_by(ProductMentionLog.mentioned_at.desc()).limit(limit)
    )).scalars().all()
    out = []
    for i in rows:
        sender_display, phones_in_msg, all_contacts = contacts_for(i.sender_phone or "", i.message_text or "")
        out.append({
            "id": str(i.id), "product": i.product_name, "sender": sender_display,
            "sender_name": i.sender_name, "group": i.group_name,
            "time": str(i.mentioned_at), "text": i.message_text,
            "sender_phone": sender_display, "phones_in_message": phones_in_msg,
            "all_contacts": all_contacts,
        })
    return out


@router.delete("/product-mentions")
async def clear_product_mentions(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(ProductMentionLog))
    await db.commit()
    return {"cleared": True}


@router.get("/top-products")
async def top_repeated_products(limit: int = 150, days: int = 30, db: AsyncSession = Depends(get_db)):
    """Most-frequently-mentioned products across groups (from product_mention_logs)."""
    from datetime import timedelta
    from app.utils.shamsi import to_shamsi
    limit = max(1, min(limit, 500))
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (await db.execute(
        select(
            ProductMentionLog.product_name,
            func.count().label("mention_count"),
            func.count(func.distinct(ProductMentionLog.group_chat_id)).label("group_count"),
            func.count(func.distinct(ProductMentionLog.sender_phone)).label("sender_count"),
            func.max(ProductMentionLog.mentioned_at).label("last_mention"),
        )
        .where(ProductMentionLog.mentioned_at >= cutoff)
        .group_by(ProductMentionLog.product_name)
        .order_by(func.count().desc())
        .limit(limit)
    )).all()
    return {
        "total_products": len(rows),
        "period_days": days,
        "products": [
            {
                "rank": i + 1,
                "product_name": r.product_name,
                "mention_count": r.mention_count,
                "group_count": r.group_count,
                "sender_count": r.sender_count,
                "last_mention_shamsi": to_shamsi(r.last_mention),
            }
            for i, r in enumerate(rows)
        ],
    }


@router.get("/product-sellers")
async def product_sellers(product_name: str, days: int = 30, limit: int = 100,
                          db: AsyncSession = Depends(get_db)):
    """All sellers who advertised a given product: contact, time (Shamsi), group.
    Powers the 'مشاهده فروشندگان اخیر' modal in the top-products table."""
    from datetime import timedelta
    from app.services.phone_extract import contacts_for
    from app.utils.shamsi import to_shamsi

    limit = max(1, min(limit, 500))
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (await db.execute(
        select(ProductMentionLog)
        .where(ProductMentionLog.product_name == product_name)
        .where(ProductMentionLog.mentioned_at >= cutoff)
        .order_by(ProductMentionLog.mentioned_at.desc())
        .limit(limit)
    )).scalars().all()

    sellers = []
    for m in rows:
        sender_display, _phones, all_contacts = contacts_for(m.sender_phone or "", m.message_text or "")
        sellers.append({
            "sender_name": m.sender_name or "",
            "sender_phone": sender_display,
            "all_contacts": all_contacts,
            "group_name": m.group_name or "",
            "message_preview": (m.message_text or "")[:120],
            "time_shamsi": to_shamsi(m.mentioned_at),
        })

    return {"product_name": product_name, "total_sellers": len(sellers), "sellers": sellers}


@router.get("/best-hours")
async def best_hours(days: int = 30, db: AsyncSession = Depends(get_db)):
    """V13.3 — read/delivered rate by Tehran hour-of-day (from campaign_contacts.sent_at).
    best_hours lists the top-3 hours by read% among hours with a minimum sample size."""
    from datetime import timedelta
    from sqlalchemy import case
    from app.models.campaign import CampaignContact
    MIN_SAMPLE = 5
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    # sent_at is stored UTC (naive) → interpret as UTC then convert to Tehran local.
    hour_expr = func.extract(
        "hour", func.timezone("Asia/Tehran", func.timezone("UTC", CampaignContact.sent_at))
    )
    rows = (await db.execute(
        select(
            hour_expr.label("hr"),
            func.count().label("sent"),
            func.sum(case((CampaignContact.delivery_status.in_(["delivered", "read"]), 1), else_=0)).label("delivered"),
            func.sum(case((CampaignContact.delivery_status == "read", 1), else_=0)).label("read"),
        )
        .where(CampaignContact.sent_at.isnot(None), CampaignContact.sent_at >= cutoff)
        .group_by(hour_expr)
    )).all()
    by_map = {int(r.hr): r for r in rows if r.hr is not None}
    by_hour = []
    for h in range(24):
        r = by_map.get(h)
        sent = int(r.sent) if r else 0
        delivered = int(r.delivered or 0) if r else 0
        read = int(r.read or 0) if r else 0
        by_hour.append({
            "hour": h,
            "sent": sent,
            "delivered_pct": round(100 * delivered / sent, 1) if sent else 0.0,
            "read_pct": round(100 * read / sent, 1) if sent else 0.0,
        })
    best = sorted(
        [b for b in by_hour if b["sent"] >= MIN_SAMPLE],
        key=lambda b: (b["read_pct"], b["delivered_pct"]), reverse=True,
    )[:3]
    return {
        "by_hour": by_hour,
        "best_hours": [b["hour"] for b in best],
        "min_sample": MIN_SAMPLE,
        "period_days": days,
    }


# ── Products (for the Products page) ───────────────────────
@router.get("/products")
async def get_products_by_brand():
    """Products grouped by brand, sorted cheap→expensive within each brand (Feature 43).
    Degrades gracefully (brand → 'سایر', empty list) if Supabase is unreachable."""
    import httpx
    from app.config import settings

    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }
    products_url = (
        f"{settings.supabase_url}/rest/v1/products"
        f"?is_active=eq.true&stock_status=neq.unavailable"
        f"&select=id,name,model,capacity,brand_id,category"
    )
    brands_url = f"{settings.supabase_url}/rest/v1/brands?select=id,name&is_active=eq.true"

    products, brands = [], {}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            pr = await c.get(products_url, headers=headers)
            products = pr.json() if pr.status_code == 200 else []
            try:
                br = await c.get(brands_url, headers=headers)
                if br.status_code == 200:
                    brands = {b["id"]: b["name"] for b in br.json()}
            except Exception:
                brands = {}  # brands table may not be granted to anon — fall back
    except Exception as e:
        print(f"[Reporting] products-by-brand fetch failed: {e}")
        return []

    # Prices
    price_map = {}
    try:
        prices_url = f"{settings.supabase_url}/rest/v1/product_computed_prices_public?select=product_id,rounded_sale_price"
        async with httpx.AsyncClient(timeout=10) as c:
            pr2 = await c.get(prices_url, headers=headers)
            if pr2.status_code == 200:
                for row in pr2.json():
                    price_map[row["product_id"]] = row.get("rounded_sale_price")
    except Exception:
        pass

    grouped = {}
    for p in products:
        brand_name = brands.get(p.get("brand_id", ""), "سایر")
        price = price_map.get(p["id"])
        grouped.setdefault(brand_name, []).append({
            "id": p["id"],
            "name": p.get("name", ""),
            "model": p.get("model", ""),
            "capacity": p.get("capacity", ""),
            "price": price,
            "price_formatted": f"{price:,}" if price else None,
        })

    result = []
    for brand_name in sorted(grouped.keys()):
        items = sorted(grouped[brand_name], key=lambda x: (x["price"] is None, x["price"] or 0))
        result.append({"brand": brand_name, "product_count": len(items), "products": items})
    return result


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
