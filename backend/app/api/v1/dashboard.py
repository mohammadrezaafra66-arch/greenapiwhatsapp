from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.campaign import Campaign, CampaignContact, MessageStatus
from app.models.inbox import InboxMessage
from app.services.rate_limiter import get_current_tehran_hour, get_max_per_hour_for_current_time

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Real-time dashboard statistics."""

    # Account stats
    acc_result = await db.execute(select(Account))
    accounts = acc_result.scalars().all()

    # Campaign stats
    camp_result = await db.execute(
        select(func.count()).where(Campaign.status == "running")
    )
    active_campaigns = camp_result.scalar()

    # Messages sent today (sum across all accounts)
    sent_today = sum(a.sent_today for a in accounts)

    # Current rate limit
    current_hour = get_current_tehran_hour()
    max_per_hour = get_max_per_hour_for_current_time()

    # Inbox count (last 24h)
    from datetime import datetime, timedelta
    inbox_result = await db.execute(
        select(func.count()).where(
            InboxMessage.received_at >= datetime.utcnow() - timedelta(hours=24)
        )
    )
    inbox_count = inbox_result.scalar()

    return {
        "accounts": {
            "total": len(accounts),
            "active": sum(1 for a in accounts if a.status == AccountStatus.active),
            "banned": sum(1 for a in accounts if a.status == AccountStatus.banned),
            "detail": [
                {
                    "name": a.name,
                    "phone": a.phone,
                    "status": a.status,
                    "sent_today": a.sent_today,
                    "daily_limit": a.computed_daily_limit,
                }
                for a in accounts
            ]
        },
        "campaigns": {
            "active": active_campaigns,
        },
        "messages": {
            "sent_today": sent_today,
            "inbox_24h": inbox_count,
        },
        "rate_limiter": {
            "tehran_hour": current_hour,
            "max_per_hour": max_per_hour,
            "is_sending_allowed": max_per_hour > 0,
        }
    }
