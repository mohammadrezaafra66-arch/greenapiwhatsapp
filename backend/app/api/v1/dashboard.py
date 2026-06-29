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
