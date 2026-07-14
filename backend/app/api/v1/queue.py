"""V14 FEATURE 20 — send-queue management (⭐ emergency stop).

The queue Green API holds before WhatsApp delivery (messages persist ~24h).
GET summary (all accounts) drives the dashboard banner; per-account GET shows the
contents; DELETE clears it (an emergency stop for a wrong campaign).
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient

logger = logging.getLogger("afrakala.queue")
router = APIRouter(prefix="/queue", tags=["queue"])


async def _account(account_id: str, db: AsyncSession) -> Account:
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    return account


# NOTE: register the literal "/summary" BEFORE "/{account_id}" so it isn't captured.
@router.get("/summary")
async def queue_summary(db: AsyncSession = Depends(get_db)):
    """Per-account queued-message counts (for the dashboard banner + queue page)."""
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    items = []
    total = 0
    for a in accounts:
        try:
            n = await GreenAPIClient(a.instance_id, a.api_token).get_messages_count()
        except Exception:
            n = 0
        total += n or 0
        items.append({"account_id": str(a.id), "name": a.name, "count": n or 0})
    return {"total": total, "accounts": items}


@router.get("/{account_id}")
async def show_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    queue = []
    try:
        queue = await client.show_messages_queue()
    except Exception as e:
        logger.warning("showMessagesQueue failed for %s: %s", account.instance_id, e)
    try:
        count = await client.get_messages_count()
    except Exception:
        count = len(queue) if isinstance(queue, list) else 0
    # getWebhooksBufferCount is plan-gated on this instance (probe: 403) — degrade.
    webhooks_count = None
    try:
        webhooks_count = await client.get_webhooks_count()
    except Exception:
        webhooks_count = None
    return {
        "account": account.name,
        "account_id": str(account.id),
        "count": count,
        "queue": queue if isinstance(queue, list) else [],
        "webhooks_count": webhooks_count,
    }


@router.delete("/{account_id}")
async def clear_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        ok = await client.clear_messages_queue()
    except Exception as e:
        logger.error("clearMessagesQueue failed for %s: %s", account.instance_id, e)
        raise HTTPException(502, "خالی کردن صف ناموفق بود")
    return {"cleared": ok}
