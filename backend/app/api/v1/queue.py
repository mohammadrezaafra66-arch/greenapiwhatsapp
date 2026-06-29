import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.account import Account
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/queue", tags=["queue"])


async def _account(account_id: str, db: AsyncSession) -> Account:
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@router.get("/{account_id}")
async def show_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    queue = await client.show_messages_queue()
    return {"account": account.name, "queue": queue, "count": len(queue) if isinstance(queue, list) else 0}


@router.delete("/{account_id}")
async def clear_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.clear_messages_queue()
    return {"cleared": ok}
