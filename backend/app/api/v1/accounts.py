from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.config import settings
import uuid

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AutoReplyUpdate(BaseModel):
    auto_reply_enabled: bool | None = None
    auto_reply_message: str | None = None
    auto_reply_outside_hours: bool | None = None
    warmup_enabled: bool | None = None
    polling_enabled: bool | None = None


@router.get("/")
async def list_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    accounts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "instance_id": a.instance_id,
            "phone": a.phone,
            "status": a.status,
            "sent_today": a.sent_today,
            "received_today": a.received_today,
            "daily_limit": a.computed_daily_limit,
            "days_active": a.days_active,
            "warmup_enabled": a.warmup_enabled,
            "auto_reply_enabled": a.auto_reply_enabled,
            "auto_reply_outside_hours": a.auto_reply_outside_hours,
        }
        for a in accounts
    ]


@router.post("/")
async def create_account(
    name: str,
    instance_id: str,
    api_token: str,
    db: AsyncSession = Depends(get_db)
):
    account = Account(name=name, instance_id=instance_id, api_token=api_token)
    db.add(account)
    await db.commit()
    await db.refresh(account)

    webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/{instance_id}"
    client = GreenAPIClient(instance_id, api_token)
    try:
        await client.set_webhook(webhook_url)
    except Exception as e:
        print(f"Warning: Could not set webhook: {e}")

    return {"id": str(account.id), "name": account.name, "status": account.status}


async def _get_account(account_id: str, db: AsyncSession) -> Account:
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@router.get("/{account_id}/status")
async def check_account_status(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    state = await client.get_state()
    if state == "authorized":
        account.status = AccountStatus.active
    elif state == "blocked":
        account.status = AccountStatus.banned
    elif state == "notAuthorized":
        account.status = AccountStatus.disconnected
    await db.commit()
    return {"state": state, "status": account.status}


@router.get("/{account_id}/qr")
async def get_account_qr(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    qr = await client.get_qr()
    return {"qr": qr}


@router.post("/{account_id}/reboot")
async def reboot_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.reboot()
    return {"rebooted": ok}


@router.post("/{account_id}/logout")
async def logout_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.logout()
    account.status = AccountStatus.disconnected
    await db.commit()
    return {"logged_out": ok}


@router.post("/{account_id}/check-whatsapp-bulk")
async def check_whatsapp_bulk(
    account_id: str,
    contact_ids: list[str],
    db: AsyncSession = Depends(get_db)
):
    """Batch-check whether contacts have WhatsApp using this account."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    from datetime import datetime
    results = []
    for cid in contact_ids:
        contact = await db.get(Contact, uuid.UUID(cid))
        if not contact:
            continue
        try:
            has_wa = await client.check_whatsapp(contact.phone)
            contact.has_whatsapp = has_wa
            contact.whatsapp_checked_at = datetime.utcnow()
            results.append({"id": cid, "phone": contact.phone, "has_whatsapp": has_wa})
        except Exception as e:
            results.append({"id": cid, "phone": contact.phone, "error": str(e)})
    await db.commit()
    return {"checked": len(results), "results": results}


@router.put("/{account_id}/auto-reply")
async def update_auto_reply(account_id: str, payload: AutoReplyUpdate, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    if payload.auto_reply_enabled is not None:
        account.auto_reply_enabled = payload.auto_reply_enabled
    if payload.auto_reply_message is not None:
        account.auto_reply_message = payload.auto_reply_message
    if payload.auto_reply_outside_hours is not None:
        account.auto_reply_outside_hours = payload.auto_reply_outside_hours
    if payload.warmup_enabled is not None:
        account.warmup_enabled = payload.warmup_enabled
    if payload.polling_enabled is not None:
        account.polling_enabled = payload.polling_enabled
    await db.commit()
    return {
        "auto_reply_enabled": account.auto_reply_enabled,
        "auto_reply_message": account.auto_reply_message,
        "auto_reply_outside_hours": account.auto_reply_outside_hours,
        "warmup_enabled": account.warmup_enabled,
        "polling_enabled": account.polling_enabled,
    }


@router.get("/{account_id}/queue")
async def get_account_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    queue = await client.show_messages_queue()
    return {"queue": queue, "count": len(queue) if isinstance(queue, list) else 0}


@router.delete("/{account_id}/queue")
async def clear_account_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.clear_messages_queue()
    return {"cleared": ok}


@router.post("/{account_id}/send-typing")
async def send_typing(account_id: str, phone: str, seconds: int = 3, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.send_typing(phone, seconds)
    return {"typing_sent": ok}


@router.post("/{account_id}/messages/{message_id}/edit")
async def edit_message(account_id: str, message_id: str, phone: str, new_text: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.edit_message(phone, message_id, new_text)
    return {"edited": ok}


@router.delete("/{account_id}/messages/{message_id}")
async def delete_message(account_id: str, message_id: str, phone: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.delete_message(phone, message_id)
    return {"deleted": ok}


@router.post("/{account_id}/contacts/add")
async def add_contact_to_phonebook(account_id: str, phone: str, first_name: str, last_name: str = "", db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.add_contact(phone, first_name, last_name)
    return {"added": ok}


@router.post("/{account_id}/token/refresh")
async def refresh_api_token(account_id: str, db: AsyncSession = Depends(get_db)):
    """Generate a new API token. Old token stays valid ~1h. Update DB immediately."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    new_token = await client.update_api_token()
    if new_token:
        account.api_token = new_token
        await db.commit()
    return {"new_token": new_token, "updated_in_db": bool(new_token)}


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    await db.delete(account)
    await db.commit()
    return {"success": True}
