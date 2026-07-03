"""
Journal endpoints: fetch message history from Green API's last message logs.
Also supports downloading files from incoming messages.
"""
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/journals", tags=["journals"])


def _green_error(e: Exception) -> str:
    """Human-readable reason for a failed Green API call."""
    if isinstance(e, httpx.HTTPStatusError):
        return f"Green API {e.response.status_code}"
    return str(e)[:200]


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
    try:
        messages = await client.last_incoming_messages(minutes)
    except Exception as e:
        return {"account_id": account_id, "count": 0, "messages": [], "error": _green_error(e)}
    return {"account_id": account_id, "count": len(messages), "messages": messages}


@router.get("/{account_id}/outgoing")
async def get_last_outgoing(account_id: str, minutes: int = 1440, db: AsyncSession = Depends(get_db)):
    """Get outgoing messages from the last N minutes via Green API journal."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        messages = await client.last_outgoing_messages(minutes)
    except Exception as e:
        return {"account_id": account_id, "count": 0, "messages": [], "error": _green_error(e)}
    return {"account_id": account_id, "count": len(messages), "messages": messages}


@router.get("/{account_id}/chats")
async def get_chats(account_id: str, db: AsyncSession = Depends(get_db)):
    """Get list of all active chats for this account."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        chats = await client.get_chats()
    except Exception as e:
        return {"account_id": account_id, "count": 0, "chats": [], "error": _green_error(e)}
    return {"account_id": account_id, "count": len(chats), "chats": chats}


@router.post("/{account_id}/download-file")
async def download_file(account_id: str, chat_id: str, message_id: str, db: AsyncSession = Depends(get_db)):
    """Get download URL for a file from an incoming message."""
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        url = await client.download_file(chat_id, message_id)
    except Exception as e:
        raise HTTPException(502, f"Green API error: {_green_error(e)}")
    if not url:
        raise HTTPException(404, "File not found or not downloadable")
    return {"download_url": url}


@router.get("/{account_id}/queue-count")
async def get_queue_count(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    error = None
    try:
        msg_count = await client.get_messages_count()
    except Exception as e:
        msg_count, error = 0, _green_error(e)
    try:
        wh_count = await client.get_webhooks_count()
    except Exception as e:
        wh_count, error = 0, _green_error(e)
    out = {"messages_in_queue": msg_count, "webhooks_in_queue": wh_count}
    if error:
        out["error"] = error
    return out


@router.delete("/{account_id}/webhooks-queue")
async def clear_webhooks_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_active_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        ok = await client.clear_webhooks_queue()
    except Exception as e:
        return {"cleared": False, "error": _green_error(e)}
    return {"cleared": ok}
