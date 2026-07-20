"""V14 FEATURE 23 — safety incidents, protection dashboard, and the MANUAL actions
(reboot / resume / reconnect) that are never automatic and are disabled during cooldown.
"""
import uuid
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.campaign import Campaign, CampaignStatus, CampaignContact
from app.models.incident import AccountIncident
from app.services.green_api import GreenAPIClient
from app.services import governors
from app.services.account_health import health_breakdown
from app.services.incident_handler import PAUSE_REASON
from app.config import settings
from app.utils.shamsi import to_shamsi

logger = logging.getLogger("afrakala.incidents")
router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("/")
async def list_incidents(unresolved: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(AccountIncident).order_by(AccountIncident.created_at.desc()).limit(200)
    if unresolved:
        q = select(AccountIncident).where(AccountIncident.resolved.is_(False)) \
            .order_by(AccountIncident.created_at.desc()).limit(200)
    rows = (await db.execute(q)).scalars().all()
    names = {a.id: a.name for a in (await db.execute(select(Account))).scalars().all()}
    return [{
        "id": str(i.id),
        "account_id": str(i.account_id) if i.account_id else None,
        "account_name": names.get(i.account_id, "—"),
        "incident_type": i.incident_type,
        "severity": i.severity,
        "detected_via": i.detected_via,
        "auto_actions": i.auto_actions,
        "campaigns_paused": i.campaigns_paused or [],
        "queue_snapshot_count": len(i.queue_snapshot or []),
        "resolved": i.resolved,
        "created_at": to_shamsi(i.created_at),
    } for i in rows]


@router.get("/protection")
async def protection(db: AsyncSession = Depends(get_db)):
    """Per-account safety status for the «محافظت و سلامت» page."""
    accounts = (await db.execute(select(Account).where(Account.status != AccountStatus.deleted))).scalars().all()
    cutoff = datetime.utcnow() - timedelta(days=7)
    out = []
    for a in accounts:
        hb = await health_breakdown(a, db)
        total = (await db.execute(select(func.count()).select_from(CampaignContact).where(
            CampaignContact.account_id == a.id, CampaignContact.sent_at >= cutoff))).scalar() or 0
        replied = (await db.execute(select(func.count()).select_from(CampaignContact).where(
            CampaignContact.account_id == a.id, CampaignContact.sent_at >= cutoff,
            CampaignContact.replied.is_(True)))).scalar() or 0
        reply_rate = round(replied / total, 3) if total else None
        cd = governors.in_cooldown(a)
        status_val = a.status.value if hasattr(a.status, "value") else a.status
        # V36 — an instance deleted upstream in Green API is terminal: don't dress it up as a
        # cooldown/health problem, flag it so the card offers «حذف از پلتفرم».
        green_api_deleted = status_val == AccountStatus.green_api_deleted.value
        out.append({
            "account_id": str(a.id),
            "name": a.name,
            "status": status_val,
            "green_api_deleted": green_api_deleted,
            "green_api_deleted_message": "این اینستنس در Green API دیگر وجود ندارد" if green_api_deleted else None,
            "health_score": 0.0 if cd else hb["score"],
            "sent_today": hb["sent_today"],
            "effective_cap": governors.effective_daily_cap(a),
            "yellow_card_rate_7d": hb["yellow_card_rate"],
            "reply_rate_7d": reply_rate,
            "throttle_factor": a.throttle_factor or 1.0,
            "throttle_until": to_shamsi(a.throttle_until),
            "in_cooldown": cd,
            "cooldown_until": to_shamsi(a.cooldown_until),
            "incident_count_7d": a.incident_count_7d or 0,
        })
    return {"accounts": out, "auto_failover": settings.auto_failover_on_yellow_card}


@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    inc = await db.get(AccountIncident, uuid.UUID(incident_id))
    if not inc:
        raise HTTPException(404, "رویداد یافت نشد")
    inc.resolved = True
    inc.resolved_at = datetime.utcnow()
    inc.resolved_by = "manual"
    await db.commit()
    return {"ok": True}


async def _account(account_id: str, db: AsyncSession) -> Account:
    a = await db.get(Account, uuid.UUID(account_id))
    if not a:
        raise HTTPException(404, "حساب یافت نشد")
    return a


@router.post("/account/{account_id}/reboot")
async def reboot_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """MANUAL only, and DISABLED during cooldown — reboot re-triggers yellowCard."""
    a = await _account(account_id, db)
    if governors.in_cooldown(a):
        raise HTTPException(400, "در دوره خنک‌سازی نمی‌توان ری‌بوت کرد — ری‌بوت کارت زرد را برمی‌گرداند. صبر کنید تا دوره تمام شود.")
    try:
        ok = await GreenAPIClient(a.instance_id, a.api_token).reboot()
    except Exception as e:
        raise HTTPException(502, f"ری‌بوت ناموفق بود: {str(e)[:120]}")
    return {"rebooted": ok}


@router.post("/account/{account_id}/resume")
async def resume_campaigns(account_id: str, db: AsyncSession = Depends(get_db)):
    """MANUAL resume of campaigns paused by a yellowCard — blocked during cooldown."""
    a = await _account(account_id, db)
    if governors.in_cooldown(a):
        raise HTTPException(400, "در دوره خنک‌سازی نمی‌توان ارسال را ادامه داد — صبر کنید تا دوره تمام شود.")
    paused = (await db.execute(select(Campaign).where(
        Campaign.status == CampaignStatus.paused, Campaign.pause_reason == PAUSE_REASON))).scalars().all()
    resumed = 0
    for c in paused:
        c.status = CampaignStatus.running
        c.pause_reason = None
        resumed += 1
    await db.commit()
    from app.workers.tasks import task_run_campaign
    for c in paused:
        try:
            task_run_campaign.delay(str(c.id))
        except Exception:
            pass
    return {"resumed": resumed, "note": "با حجم کم شروع کنید (سقف روزانه نصف شده است)."}


@router.post("/account/{account_id}/reconnect")
async def reconnect_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """MANUAL logout so the user can re-scan the QR."""
    a = await _account(account_id, db)
    try:
        ok = await GreenAPIClient(a.instance_id, a.api_token).logout()
    except Exception as e:
        raise HTTPException(502, f"خروج ناموفق بود: {str(e)[:120]}")
    a.status = AccountStatus.disconnected
    await db.commit()
    return {"logged_out": ok}
