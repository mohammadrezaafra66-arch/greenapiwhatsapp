from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.campaign import Campaign
from app.models.inbox import InboxMessage
from app.services import rate_limiter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Real-time dashboard statistics."""
    acc_result = await db.execute(select(Account))
    accounts = acc_result.scalars().all()

    # Lazy daily reset: if an account's counters weren't reset today (Tehran),
    # zero them now. Guards against the beat cron missing (e.g. worker restarts).
    import pytz
    from datetime import datetime as _dt
    today_tehran = _dt.now(pytz.timezone("Asia/Tehran")).date()
    _reset_any = False
    for a in accounts:
        if a.last_reset_date != today_tehran:
            a.received_yesterday = a.received_today
            a.sent_today = 0
            a.received_today = 0
            a.last_reset_date = today_tehran
            _reset_any = True
    if _reset_any:
        await db.commit()

    camp_result = await db.execute(
        select(func.count()).where(Campaign.status == "running")
    )
    active_campaigns = camp_result.scalar()

    # V30 PART 8 — "کل پیام‌های ارسالی امروز" must reflect ALL of today's real outbound sends
    # (Tehran calendar day), not just the campaign counter. sum(a.sent_today) missed «همکاری تیمی»,
    # mesh, and status sends entirely (they use their own ledgers), so a TC-only day showed 0.
    from app.services.send_metrics import real_sent_today
    sent_breakdown = await real_sent_today(db)
    sent_today = sent_breakdown["total"]
    campaign_sent_today = sum(a.sent_today for a in accounts)   # kept for the per-account view
    received_today = sum(a.received_today for a in accounts)

    current_hour = rate_limiter.get_tehran_hour()
    max_per_hour = rate_limiter.get_max_per_hour()

    from datetime import datetime, timedelta
    inbox_result = await db.execute(
        select(func.count()).where(
            InboxMessage.received_at >= datetime.utcnow() - timedelta(hours=24)
        )
    )
    inbox_count = inbox_result.scalar()

    unread_result = await db.execute(
        select(func.count()).where(InboxMessage.is_read == False)
    )
    unread = unread_result.scalar()

    return {
        "accounts": {
            "total": len(accounts),
            "active": sum(1 for a in accounts if a.status == AccountStatus.active),
            "banned": sum(1 for a in accounts if a.status == AccountStatus.banned),
            "detail": [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "phone": a.phone,
                    "status": a.status,
                    "sent_today": a.sent_today,
                    "received_today": a.received_today,
                    "daily_limit": a.computed_daily_limit,
                    "warmup_enabled": a.warmup_enabled,
                    "quota_exceeded_at": str(a.quota_exceeded_at) if a.quota_exceeded_at else None,
                }
                for a in accounts
            ]
        },
        "campaigns": {"active": active_campaigns},
        "messages": {
            "sent_today": sent_today,                       # V30 PART 8 — real cross-ledger total
            "sent_today_breakdown": sent_breakdown,          # campaign / team_collaboration / mesh / status
            "campaign_sent_today": campaign_sent_today,       # legacy campaign-counter sum (per-account view)
            "received_today": received_today,
            "inbox_24h": inbox_count,
            "unread": unread,
        },
        "rate_limiter": {
            "tehran_hour": current_hour,
            "max_per_hour": max_per_hour,
            "is_sending_allowed": max_per_hour > 0,
        }
    }


@router.post("/validate-campaign")
async def validate_campaign(
    contact_count: int,
    account_ids: list[str] = Query(default=[]),
    min_delay: int = 45,
    max_delay: int = 110,
    hours_available: int = 14,  # e.g. 08:00-22:00 = 14 hours
    db: AsyncSession = Depends(get_db),
):
    """Pre-send feasibility analysis with color code, warnings, recommendations."""
    import uuid as _uuid
    import math
    from app.services.rate_limiter import DEFAULT_SCHEDULE

    accounts = []
    for aid in account_ids:
        try:
            a = await db.get(Account, _uuid.UUID(aid))
        except Exception:
            a = None
        if a and a.status == AccountStatus.active:
            accounts.append(a)

    if not accounts:
        return {"feasible": False, "reason": "هیچ حساب فعالی انتخاب نشده", "color": "red",
                "status": "❌ هیچ حساب فعالی انتخاب نشده", "summary": {}, "warnings": [], "recommendations": []}

    avg_limit = sum(a.computed_daily_limit for a in accounts) / len(accounts)
    total_daily_capacity = sum(min(a.computed_daily_limit, a.max_daily_absolute or 200) for a in accounts)
    avg_delay = (min_delay + max_delay) / 2
    msgs_per_hour = 3600 / avg_delay if avg_delay else 0
    days_needed = math.ceil(contact_count / total_daily_capacity) if total_daily_capacity > 0 else 999
    hours_needed_raw = (contact_count * avg_delay) / 3600

    warnings = []
    if total_daily_capacity < 10:
        warnings.append("⚠️ محدودیت روزانه بسیار پایین — حساب‌ها نیاز به warm-up دارند")
    if avg_delay < 30:
        warnings.append("⚠️ تاخیر کمتر از ۳۰ ثانیه خطر بلاک دارد")
    if contact_count / len(accounts) > 100:
        warnings.append(f"⚠️ هر حساب باید {contact_count // len(accounts)} پیام بفرستد — در چند روز تقسیم کنید")
    if days_needed > 30:
        warnings.append(f"⛔ با این تنظیمات {days_needed} روز طول می‌کشد")

    recommendations = []
    if days_needed > 7 and total_daily_capacity > 0:
        per_acc = total_daily_capacity / len(accounts)
        extra = math.ceil(contact_count / (7 * per_acc)) - len(accounts) if per_acc else 0
        if extra > 0:
            recommendations.append(f"💡 برای تکمیل در ۷ روز: {extra} حساب اضافی نیاز دارید")
    if avg_delay < 45:
        recommendations.append("💡 تاخیر را به حداقل ۴۵ ثانیه افزایش دهید")

    if days_needed <= 7 and len(warnings) == 0:
        color, feasible, status = "green", True, "✅ تنظیمات مناسب است"
    elif days_needed <= 30 and not any("⛔" in w for w in warnings):
        color, feasible, status = "amber", True, "⚠️ ممکن است اما نیاز به بررسی دارد"
    else:
        color, feasible, status = "red", False, "❌ تنظیمات مناسب نیست — تغییر لازم است"

    return {
        "feasible": feasible,
        "color": color,
        "status": status,
        "summary": {
            "contact_count": contact_count,
            "active_accounts": len(accounts),
            "total_daily_capacity": total_daily_capacity,
            "avg_daily_per_account": round(avg_limit, 1),
            "avg_delay_seconds": avg_delay,
            "msgs_per_hour_per_account": round(msgs_per_hour, 1),
            "estimated_days": days_needed,
            "estimated_hours_raw": round(hours_needed_raw, 1),
        },
        "warnings": warnings,
        "recommendations": recommendations,
    }


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db)):
    """C3 — system health for the dashboard widget (reachable via the /api/v1
    proxy): DB, Redis, and Celery worker heartbeat."""
    from sqlalchemy import text as _text
    out = {"status": "ok", "database": "ok", "redis": "ok", "workers": []}
    try:
        await db.execute(_text("SELECT 1"))
    except Exception:
        out["database"] = "error"
        out["status"] = "degraded"
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        await r.ping()
    except Exception:
        out["redis"] = "error"
        out["status"] = "degraded"
    try:
        from app.workers.celery_app import celery_app
        pong = celery_app.control.ping(timeout=1.0)
        out["workers"] = [list(w.keys())[0] for w in pong] if pong else []
        if not out["workers"]:
            out["status"] = "degraded"
    except Exception:
        out["status"] = "degraded"
    return out


@router.get("/deliverability")
async def deliverability(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Delivery-status breakdown for sent campaign messages over the last N days.
    Buckets come from campaign_contacts.delivery_status (set by the
    outgoingMessageStatus webhook): delivered / read / yellowCard / failed / pending."""
    from datetime import datetime, timedelta
    from sqlalchemy import case
    from app.models.campaign import CampaignContact

    cutoff = datetime.utcnow() - timedelta(days=days)
    ds = CampaignContact.delivery_status

    def bucket(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    rows = (await db.execute(
        select(
            CampaignContact.account_id,
            func.count().label("total"),
            bucket(ds == "delivered").label("delivered"),
            bucket(ds == "read").label("read"),
            bucket(ds == "yellowCard").label("yellow_card"),
            bucket(ds == "failed").label("failed"),
            bucket((ds.is_(None)) | (ds == "sent")).label("pending"),
        )
        .where(CampaignContact.sent_at.isnot(None), CampaignContact.sent_at >= cutoff)
        .group_by(CampaignContact.account_id)
    )).all()

    # account names
    accs = (await db.execute(select(Account))).scalars().all()
    names = {a.id: a.name for a in accs}

    def pct(n, total):
        return round(n / total * 100, 1) if total else 0.0

    total_sent = sum(r.total for r in rows)
    total_delivered = sum(r.delivered for r in rows)
    total_read = sum(r.read for r in rows)
    total_yellow = sum(r.yellow_card for r in rows)
    total_failed = sum(r.failed for r in rows)
    total_pending = sum(r.pending for r in rows)

    per_account = [
        {
            "account_id": str(r.account_id) if r.account_id else None,
            "name": names.get(r.account_id, "نامشخص"),
            "total": r.total,
            "delivered": r.delivered,
            "read": r.read,
            "yellow_card": r.yellow_card,
            "failed": r.failed,
            "pending": r.pending,
            "yellow_card_pct": pct(r.yellow_card, r.total),
        }
        for r in rows
    ]
    per_account.sort(key=lambda x: x["total"], reverse=True)

    return {
        "window_days": days,
        "total_sent": total_sent,
        "delivered": {"count": total_delivered, "pct": pct(total_delivered, total_sent)},
        "read": {"count": total_read, "pct": pct(total_read, total_sent)},
        "yellow_card": {"count": total_yellow, "pct": pct(total_yellow, total_sent)},
        "failed": {"count": total_failed, "pct": pct(total_failed, total_sent)},
        "pending": {"count": total_pending, "pct": pct(total_pending, total_sent)},
        "per_account": per_account,
    }


@router.get("/product-mentions/recent")
async def get_product_mentions(limit: int = 50, db: AsyncSession = Depends(get_db)):
    from app.models.reporting import ProductMentionLog
    from app.services.phone_extract import contacts_for
    result = await db.execute(
        select(ProductMentionLog).order_by(ProductMentionLog.mentioned_at.desc()).limit(limit)
    )
    items = result.scalars().all()
    out = []
    for i in items:
        sender_display, phones_in_msg, all_contacts = contacts_for(i.sender_phone or "", i.message_text or "")
        out.append({
            "product": i.product_name, "sender": sender_display, "sender_name": i.sender_name,
            "group": i.group_name, "time": str(i.mentioned_at), "text": i.message_text,
            # Feature A — contact info (sender phone + numbers found inside the message)
            "sender_phone": sender_display, "phones_in_message": phones_in_msg,
            "all_contacts": all_contacts,
        })
    return out


@router.get("/ai-stats")
async def ai_stats():
    """AI token usage per provider over the last 24h."""
    from app.services.gpt_service import get_ai_stats
    data = await get_ai_stats()
    return [
        {"provider": provider, "calls": v["calls"], "total_tokens": v["total_tokens"], "errors": v["errors"]}
        for provider, v in data.items()
    ]


@router.get("/ai-providers")
async def ai_providers():
    """Which AI providers are configured (key set). Never returns key values."""
    from app.services.gpt_service import configured_providers
    return configured_providers()


@router.get("/rate-limits")
async def get_rate_limits():
    return {
        "schedule": rate_limiter.DEFAULT_SCHEDULE,
        "current_hour": rate_limiter.get_tehran_hour(),
        "current_max": rate_limiter.get_max_per_hour(),
    }


class RateSlot(BaseModel):
    hour_start: int
    hour_end: int
    max_per_hour: int


@router.put("/rate-limits")
async def update_rate_limits(schedule: list[RateSlot]):
    """Replace the in-memory send schedule (resets on restart)."""
    rate_limiter.DEFAULT_SCHEDULE = [s.model_dump() for s in schedule]
    return {"schedule": rate_limiter.DEFAULT_SCHEDULE}
