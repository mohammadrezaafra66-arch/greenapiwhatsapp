import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.status_send import StatusSend
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/statuses", tags=["statuses"])


class TextStatusBody(BaseModel):
    text: str
    bg_color: str = "#25D366"
    account_ids: list[str] | None = None  # None = all active accounts


class ImageStatusBody(BaseModel):
    image_url: str
    caption: str = ""
    account_ids: list[str] | None = None


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
            msg_id = await client.send_status_text(body.text, body.bg_color)
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
            msg_id = await client.send_status_image(body.image_url, body.caption)
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
async def send_voice_status(audio_url: str, db: AsyncSession = Depends(get_db)):
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    accounts = acc_result.scalars().all()
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        msg_id = await client.send_voice_status(audio_url)
        results.append({"account": account.name, "message_id": msg_id})
    return {"sent": len(results), "results": results}


@router.delete("/{message_id}")
async def delete_status(message_id: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.delete_status(message_id)
    return {"deleted": ok}


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
    return {"count": len(statuses), "statuses": statuses}


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
