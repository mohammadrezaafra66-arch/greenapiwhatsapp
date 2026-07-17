"""V26 — group-monitoring API (listener designation, monitored groups, keywords,
messages, admin alerts). Grown across PART 1 (listener) and PART 5 (UI endpoints)."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.account import Account
from app.models.group_monitor import (
    MonitoredGroup, GroupMessage, GroupKeyword, GroupPredefinedReply, GroupForbiddenAlert,
    CONVERSATION_MODES, KEYWORD_KINDS, CONVERSATION_MODE_OFF,
)

router = APIRouter(prefix="/group-monitor", tags=["group-monitor"])


# ── PART 1 — listener designation ────────────────────────────────────────────
class ListenerBody(BaseModel):
    is_listener: bool = True


@router.post("/listener/{account_id}")
async def set_listener_role(account_id: str, body: ListenerBody, db: AsyncSession = Depends(get_db)):
    """Designate (or clear) an account as a dedicated group-monitoring listener.
    Enforces the one-account-one-role guard (mutually exclusive with warm-up/campaign)."""
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    from app.services.listener_service import set_listener
    ok, err = await set_listener(db, acc, body.is_listener)
    if not ok:
        raise HTTPException(400, err)
    await db.commit()

    webhook_applied = False
    if acc.is_listener:
        # Enable the incomingWebhook setting so group messages reach the backend. This is
        # webhook-only: polling is NEVER touched and the webhook URL / ngrok is NOT changed.
        try:
            from app.services.green_api import GreenAPIClient
            client = GreenAPIClient(acc.instance_id, acc.api_token)
            webhook_applied = await client.set_settings({"incomingWebhook": "yes"})
        except Exception:
            webhook_applied = False
    return {"account_id": account_id, "is_listener": acc.is_listener,
            "incoming_webhook_applied": bool(webhook_applied)}


@router.get("/listeners")
async def list_listeners(db: AsyncSession = Depends(get_db)):
    """All accounts currently marked as listeners."""
    accs = (await db.execute(select(Account).where(Account.is_listener.is_(True)))).scalars().all()
    return [{"id": str(a.id), "name": a.name, "instance_id": a.instance_id, "phone": a.phone}
            for a in accs]
