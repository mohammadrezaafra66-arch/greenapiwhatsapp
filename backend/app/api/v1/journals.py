"""
Journal endpoints: fetch message history from Green API's last message logs.
Also supports downloading files from incoming messages.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/journals", tags=["journals"])


async def _get_active_account(account_id: str, db: AsyncSession) -> Account:
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    if account.status != AccountStatus.active:
        raise HTTPException(400, "Account not active")
    return account


@router.get("/{account_id}/incoming")
async def get_last_incoming(account_id: str, minutes: int = 1440, db: AsyncSession = Depends(get_db)):
    """Get incoming messages from the last N minutes via Green API journal."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    messages = await client.last_incoming_messages(minutes)
    return {"account_id": account_id, "count": len(messages), "messages": messages}


@router.get("/{account_id}/outgoing")
async def get_last_outgoing(account_id: str, minutes: int = 1440, db: AsyncSession = Depends(get_db)):
    """Get outgoing messages from the last N minutes via Green API journal."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    messages = await client.last_outgoing_messages(minutes)
    return {"account_id": account_id, "count": len(messages), "messages": messages}


@router.get("/{account_id}/chats")
async def get_chats(account_id: str, db: AsyncSession = Depends(get_db)):
    """Get list of all active chats for this account."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    chats = await client.get_chats()
    return {"account_id": account_id, "count": len(chats), "chats": chats}


@router.post("/{account_id}/download-file")
async def download_file(account_id: str, chat_id: str, message_id: str, db: AsyncSession = Depends(get_db)):
    """Get download URL for a file from an incoming message."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    url = await client.download_file(chat_id, message_id)
    if not url:
        raise HTTPException(404, "File not found or not downloadable")
    return {"download_url": url}


@router.get("/{account_id}/queue-count")
async def get_queue_count(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    msg_count = await client.get_messages_count()
    wh_count = await client.get_webhooks_count()
    return {"messages_in_queue": msg_count, "webhooks_in_queue": wh_count}


@router.delete("/{account_id}/webhooks-queue")
async def clear_webhooks_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.clear_webhooks_queue()
    return {"cleared": ok}
