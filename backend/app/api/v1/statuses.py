import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.status_send import StatusSend
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/statuses", tags=["statuses"])
logger = logging.getLogger("afrakala.statuses")


async def _persist_incoming(db: AsyncSession, instance_id: str, statuses: list[dict]) -> None:
    """V40 PART 1 — persist fetched incoming stories + download their media locally (best-effort).
    Never lets a persistence error break the live fetch the UI depends on."""
    try:
        from app.services.story_media import persist_incoming_statuses
        await persist_incoming_statuses(db, instance_id, statuses)
        await db.commit()
    except Exception as e:
        logger.warning("persist incoming statuses failed for %s: %s", instance_id, e)


class TextStatusBody(BaseModel):
    text: str
    bg_color: str = "#25D366"
    account_ids: list[str] | None = None  # None = all active accounts
    participants: list[str] | None = None  # V14 F19 — null/[] = public to all contacts


class ImageStatusBody(BaseModel):
    image_url: str
    caption: str = ""
    account_ids: list[str] | None = None
    participants: list[str] | None = None


class VoiceStatusBody(BaseModel):
    audio_url: str
    bg_color: str = "#228B22"
    account_ids: list[str] | None = None
    participants: list[str] | None = None


async def _target_accounts(account_ids, db: AsyncSession):
    if account_ids:
        accounts = []
        for aid in account_ids:
            import uuid as _uuid
            a = await db.get(Account, _uuid.UUID(aid))
            if a:
                accounts.append(a)
        return accounts
    result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    return result.scalars().all()


@router.post("/text")
async def send_text_status(body: TextStatusBody, db: AsyncSession = Depends(get_db)):
    accounts = await _target_accounts(body.account_ids, db)
    if not accounts:
        raise HTTPException(400, "No target accounts")
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        try:
            msg_id = await client.send_text_status_full(body.text, body.bg_color, participants=body.participants)
            db.add(StatusSend(
                account_id=account.id, instance_id=account.instance_id,
                status_type="text", content=body.text, green_api_message_id=msg_id
            ))
            results.append({"account": account.name, "message_id": msg_id})
        except Exception as e:
            results.append({"account": account.name, "error": str(e)})
    await db.commit()
    return {"sent_to": len(results), "results": results}


@router.post("/image")
async def send_image_status(body: ImageStatusBody, db: AsyncSession = Depends(get_db)):
    accounts = await _target_accounts(body.account_ids, db)
    if not accounts:
        raise HTTPException(400, "No target accounts")
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        try:
            msg_id = await client.send_media_status_full(body.image_url, caption=body.caption, participants=body.participants)
            db.add(StatusSend(
                account_id=account.id, instance_id=account.instance_id,
                status_type="image", content=body.caption, media_url=body.image_url,
                green_api_message_id=msg_id
            ))
            results.append({"account": account.name, "message_id": msg_id})
        except Exception as e:
            results.append({"account": account.name, "error": str(e)})
    await db.commit()
    return {"sent_to": len(results), "results": results}


@router.post("/voice")
async def send_voice_status(body: VoiceStatusBody, db: AsyncSession = Depends(get_db)):
    accounts = await _target_accounts(body.account_ids, db)
    if not accounts:
        raise HTTPException(400, "No target accounts")
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        try:
            msg_id = await client.send_voice_status_full(body.audio_url, bg_color=body.bg_color, participants=body.participants)
            db.add(StatusSend(
                account_id=account.id, instance_id=account.instance_id,
                status_type="voice", content=body.audio_url, media_url=body.audio_url,
                green_api_message_id=msg_id
            ))
            results.append({"account": account.name, "message_id": msg_id})
        except Exception as e:
            results.append({"account": account.name, "error": str(e)})
    await db.commit()
    return {"sent_to": len(results), "results": results}


@router.delete("/{message_id}")
async def delete_status(message_id: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.delete_status(message_id)
    return {"deleted": ok}


@router.get("/history/{account_id}")
async def status_history(account_id: str, db: AsyncSession = Depends(get_db)):
    """Posted status history from Green API for this account (last 7 days)."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        statuses = await client.get_outgoing_statuses(10080)
    except Exception as e:
        msg = "دریافت تاریخچه استوری برای این حساب ممکن نیست"
        if "403" in str(e):
            msg = "این قابلیت در پلن Green API این حساب فعال نیست (خطای ۴۰۳)"
        return {"account": account.name, "statuses": [], "error": msg}
    return {"account": account.name, "statuses": statuses}


@router.get("/scheduled/{account_id}")
async def scheduled_statuses(account_id: str, db: AsyncSession = Depends(get_db)):
    """Future scheduled statuses for this account (from status_schedules)."""
    from app.models.status_schedule import StatusSchedule
    from app.utils.shamsi import to_shamsi
    result = await db.execute(
        select(StatusSchedule)
        .where(StatusSchedule.account_id == uuid.UUID(account_id))
        .where(StatusSchedule.is_active == True)
        .order_by(StatusSchedule.next_run_at.nullslast())
    )
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "status_type": s.status_type,
            "content_type": s.content_type,
            "intro_subtype": s.intro_subtype,
            "next_run_shamsi": to_shamsi(s.next_run_at),
            "days_of_week": s.days_of_week,
            "specific_dates": s.specific_dates,
            "times": s.times,
            "is_active": s.is_active,
        }
        for s in result.scalars().all()
    ]


@router.get("/incoming")
async def incoming_statuses(account_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """Fetch incoming WhatsApp statuses (Green API getIncomingStatuses). Account is
    resolved from the query param, else the default account, else the first active."""
    account = None
    if account_id:
        account = await db.get(Account, uuid.UUID(account_id))
    if account is None:
        account = (await db.execute(
            select(Account).where(Account.is_default == True)
        )).scalars().first()
    if account is None:
        account = (await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )).scalars().first()
    if account is None:
        raise HTTPException(400, "هیچ حساب فعالی برای دریافت استوری‌ها موجود نیست")
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        statuses = await client.get_incoming_statuses()
    except Exception as e:
        # Green API returns 403 for this method on some plans/tiers — degrade
        # gracefully instead of a 500 so the UI can show a friendly message.
        msg = "دریافت استوری‌های ورودی برای این حساب ممکن نیست"
        if "403" in str(e):
            msg = "این قابلیت در پلن Green API این حساب فعال نیست (خطای ۴۰۳)"
        return {"account": account.name, "account_id": str(account.id),
                "count": 0, "statuses": [], "error": msg}
    # V40 PART 1 — persist fetched stories + download their media before the ~24h WhatsApp expiry.
    await _persist_incoming(db, account.instance_id, statuses)
    return {
        "account": account.name,
        "account_id": str(account.id),
        "count": len(statuses),
        "statuses": statuses,
    }


@router.get("/incoming/{account_id}")
async def get_incoming_statuses(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    statuses = await client.get_incoming_statuses()
    # V40 PART 1 — persist fetched stories + download their media locally.
    await _persist_incoming(db, account.instance_id, statuses)
    return {"count": len(statuses), "statuses": statuses}


@router.get("/media/{status_row_id}")
async def get_status_media(status_row_id: str, db: AsyncSession = Depends(get_db)):
    """V40 PART 1 — serve the locally-persisted story image (never the expiring WhatsApp URL)."""
    from app.models.received_status import ReceivedStatus
    row = await db.get(ReceivedStatus, uuid.UUID(status_row_id))
    if row is None or not row.local_media_path or not os.path.exists(row.local_media_path):
        raise HTTPException(404, "تصویر استوری در دسترس نیست")
    return FileResponse(row.local_media_path)


@router.get("/{message_id}/stats")
async def status_statistics(message_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch view statistics for a status by its Green API message id."""
    result = await db.execute(
        select(StatusSend).where(StatusSend.green_api_message_id == message_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(404, "Status record not found")
    account = await db.get(Account, record.account_id)
    if not account:
        raise HTTPException(400, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    stats = await client.get_status_statistics(message_id)
    return stats
