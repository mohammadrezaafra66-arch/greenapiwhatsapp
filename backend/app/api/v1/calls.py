"""V14 FEATURE 24 — call logs. Missed incoming calls are HOT LEADS."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.incident import CallLog
from app.models.account import Account
from app.utils.shamsi import to_shamsi

router = APIRouter(prefix="/calls", tags=["calls"])

MISSED_STATUSES = ("missed", "declined", "offer")   # incoming with no pickUp = a lead


@router.get("/")
async def list_calls(direction: str | None = None, only_missed: bool = False,
                     limit: int = 300, db: AsyncSession = Depends(get_db)):
    q = select(CallLog).order_by(CallLog.called_at.desc().nullslast()).limit(limit)
    if direction:
        q = select(CallLog).where(CallLog.direction == direction) \
            .order_by(CallLog.called_at.desc().nullslast()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    names = {a.id: a.name for a in (await db.execute(select(Account))).scalars().all()}
    out = []
    for c in rows:
        is_missed = c.direction == "incoming" and (c.status in MISSED_STATUSES)
        if only_missed and not is_missed:
            continue
        out.append({
            "id": str(c.id),
            "account_name": names.get(c.account_id, "—"),
            "direction": c.direction,
            "from_phone": c.from_phone,
            "contact_name": c.contact_name,
            "status": c.status,
            "is_hot_lead": is_missed,
            "called_at": to_shamsi(c.called_at),
        })
    return out


@router.get("/missed-today")
async def missed_today(db: AsyncSession = Depends(get_db)):
    """Dashboard stat: «تماس‌های بی‌پاسخ امروز: N»."""
    start = datetime.utcnow() - timedelta(hours=24)
    n = (await db.execute(select(func.count()).select_from(CallLog).where(
        CallLog.direction == "incoming",
        CallLog.status.in_(MISSED_STATUSES),
        CallLog.called_at >= start,
    ))).scalar() or 0
    return {"missed_today": n}
