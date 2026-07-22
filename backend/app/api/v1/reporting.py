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
@router.get("/platform-summary")
async def platform_summary(db: AsyncSession = Depends(get_db)):
    """TG — per-platform (WhatsApp vs Telegram) account + send breakdown for the reports UI."""
    from app.models.account import Account, AccountStatus
    from app.services.platforms import summarize_by_platform
    accounts = (await db.execute(
        select(Account).where(Account.status != AccountStatus.deleted))).scalars().all()
    return summarize_by_platform(accounts)


@router.get("/daily-logs")
async def daily_logs(date: str | None = None, platform: str | None = None,
                     db: AsyncSession = Depends(get_db)):
    query = select(DailySendLog).order_by(DailySendLog.sent_at.desc())
    if date:
        try:
            d = date_type.fromisoformat(date)
            query = query.where(DailySendLog.date == d)
        except ValueError:
            raise HTTPException(400, "Invalid date (use YYYY-MM-DD)")
    if platform:
        # TG — platform breakdown: restrict to accounts on the given platform.
        from app.models.account import Account
        from app.services.platforms import normalize_platform
        query = query.where(DailySendLog.account_id.in_(
            select(Account.id).where(Account.platform == normalize_platform(platform))
        ))
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
    from app.services.price_service import get_products
    product_ids = {p.get("name"): p.get("id") for p in await get_products(500) if p.get("name")}
    rows = (await db.execute(
        select(ProductMentionLog).order_by(ProductMentionLog.mentioned_at.desc()).limit(limit)
    )).scalars().all()
    out = []
    for i in rows:
        sender_display, phones_in_msg, all_contacts = contacts_for(i.sender_phone or "", i.message_text or "")
        pid = i.product_id or product_ids.get(i.product_name)
        out.append({
            "id": str(i.id), "product": i.product_name,
            "product_id": pid,
            "in_assistant": bool(pid),
            "assistant_status": "در دستیار داریم" if pid else "خارج از دستیار",
            "sender": sender_display,
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
async def top_repeated_products(limit: int = 150, days: int = 30, source: str | None = None,
                                db: AsyncSession = Depends(get_db)):
    """Most-frequently-mentioned products across PV/groups/stories (from product_mention_logs).
    Optional `source` (pv|group|status) filters by where the mentions came from. Delegates to the
    shared product_reports service so the public /reports API can never drift."""
    from app.utils.shamsi import to_shamsi
    from app.services import product_reports as pr
    from app.services.price_service import get_products
    product_ids = {p.get("name"): p.get("id") for p in await get_products(500) if p.get("name")}
    rows = await pr.top_products_rows(db, days=days, limit=limit, source=source)
    return {
        "total_products": len(rows),
        "period_days": days,
        "source": source,
        "products": [
            {
                **({"product_id": r["product_id"] or product_ids.get(r["product_name"]),
                    "in_assistant": bool(r["product_id"] or product_ids.get(r["product_name"])),
                    "assistant_status": "در دستیار داریم" if (r["product_id"] or product_ids.get(r["product_name"])) else "خارج از دستیار"}),
                "rank": r["rank"],
                "product_name": r["product_name"],
                "mention_count": r["mention_count"],
                "group_count": r["group_count"],
                "sender_count": r["sender_count"],
                "sources": r["sources"],
                "last_mention_shamsi": to_shamsi(r["last_mention"]),
            }
            for r in rows
        ],
    }


@router.get("/product-sellers")
async def product_sellers(product_name: str, days: int = 30, limit: int = 100,
                          db: AsyncSession = Depends(get_db)):
    """All sellers who advertised a given product: contact, time (Shamsi), group.
    Powers the 'مشاهده فروشندگان اخیر' modal in the top-products table. Delegates to the shared
    product_reports service (single source of truth shared with the public /reports API)."""
    from app.utils.shamsi import to_shamsi
    from app.services import product_reports as pr
    rows = await pr.product_mentioners_rows(db, product_name=product_name, days=days, limit=limit)
    sellers = [
        {
            "sender_name": r["sender_display_name"],
            "sender_phone": r["sender_phone"],
            "all_contacts": r["all_contacts"],
            "group_name": r["group_name"],
            "message_preview": r["message_preview"],
            "time_shamsi": to_shamsi(r["mentioned_at"]),
        }
        for r in rows
    ]
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
@router.get("/supabase-status")
async def supabase_status():
    """V16 PART 1 — connectivity diagnostic so the catalog UI can distinguish
    'connected/empty' from 'disconnected' instead of always showing «محصولی یافت نشد»."""
    from app.services.supabase_health import check_supabase
    return await check_supabase()


async def _fetch_brand_groups() -> list:
    """Fetch the live catalog from Supabase, grouped by brand and sorted cheap→expensive.
    Shared by /products and /products-table. Returns [] if Supabase is unreachable."""
    import httpx
    from app.config import settings

    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }
    # NOTE: `category` (and `sku`) are NOT granted to the anon role — selecting them
    # makes the WHOLE query 401 (permission denied), which is what emptied the catalog.
    # Select only anon-readable columns. (V16 PART 2 fix.)
    products_url = (
        f"{settings.supabase_url}/rest/v1/products"
        f"?is_active=eq.true&stock_status=neq.unavailable"
        f"&select=id,name,model,capacity,brand_id"
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


@router.get("/products")
async def get_products_by_brand():
    """Products grouped by brand, sorted cheap→expensive within each brand (Feature 43).
    Degrades gracefully (empty list) if Supabase is unreachable."""
    return await _fetch_brand_groups()


@router.get("/products-table")
async def get_products_table(brands: str | None = None, search: str | None = None,
                             skip: int = 0, limit: int = 20):
    """V16 PART 2 — a flat, brand-filterable, paginated catalog table (cheapest first).
    Mirrors the contacts-table pattern. `brands` is a comma-separated list of brand names."""
    from app.services.catalog import flatten_catalog, filter_catalog, paginate, brand_names
    groups = await _fetch_brand_groups()
    all_brands = brand_names(groups)
    items = flatten_catalog(groups)
    brand_list = [b for b in (brands.split(",") if brands else []) if b.strip()]
    items = filter_catalog(items, brand_list, search)
    page = paginate(items, skip, limit)
    page["brands"] = all_brands
    return page


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
