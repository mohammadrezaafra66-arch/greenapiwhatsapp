from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from app.config import settings
import uuid

router = APIRouter(prefix="/accounts", tags=["accounts"])


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
            "daily_limit": a.computed_daily_limit,
            "days_active": a.days_active,
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

    # Configure webhook automatically
    webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/{instance_id}"
    client = GreenAPIClient(instance_id, api_token)
    try:
        await client.set_webhook(webhook_url)
    except Exception as e:
        print(f"Warning: Could not set webhook: {e}")

    return {"id": str(account.id), "name": account.name, "status": account.status}


@router.get("/{account_id}/status")
async def check_account_status(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")

    client = GreenAPIClient(account.instance_id, account.api_token)
    state = await client.get_state()

    # Update status in DB
    if state == "authorized":
        account.status = AccountStatus.active
        account.days_active += 1
    elif state == "blocked":
        account.status = AccountStatus.banned
    else:
        account.status = AccountStatus.disconnected

    await db.commit()
    return {"state": state, "status": account.status}


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    await db.delete(account)
    await db.commit()
    return {"success": True}
