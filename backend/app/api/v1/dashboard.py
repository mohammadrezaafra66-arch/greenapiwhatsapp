from fastapi import APIRouter, Depends
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

    camp_result = await db.execute(
        select(func.count()).where(Campaign.status == "running")
    )
    active_campaigns = camp_result.scalar()

    sent_today = sum(a.sent_today for a in accounts)
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
            "sent_today": sent_today,
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
    result = await db.execute(
        select(ProductMentionLog).order_by(ProductMentionLog.mentioned_at.desc()).limit(limit)
    )
    items = result.scalars().all()
    return [
        {"product": i.product_name, "sender": i.sender_phone, "sender_name": i.sender_name,
         "group": i.group_name, "time": str(i.mentioned_at), "text": i.message_text}
        for i in items
    ]


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
