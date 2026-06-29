"""
Green API Webhook receiver.
Green API POSTs all WhatsApp events here.
"""
import json
from datetime import datetime
from fastapi import APIRouter, Request, BackgroundTasks
from app.database import AsyncSessionLocal
from app.models.inbox import InboxMessage

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/{instance_id}")
async def receive_webhook(
    instance_id: str,
    request: Request,
    background_tasks: BackgroundTasks
):
    body = await request.json()
    background_tasks.add_task(process_webhook, instance_id, body)
    return {"status": "received"}


async def process_webhook(instance_id: str, payload: dict):
    """Process incoming webhook payload from Green API."""
    webhook_type = payload.get("typeWebhook", "")

    if webhook_type == "incomingMessageReceived":
        await _handle_incoming_message(instance_id, payload)
    elif webhook_type == "stateInstanceChanged":
        await _handle_state_change(instance_id, payload)
    elif webhook_type == "outgoingMessageStatus":
        await _handle_message_status(instance_id, payload)


async def _handle_incoming_message(instance_id: str, payload: dict):
    """Save incoming message to DB."""
    data = payload.get("messageData", {})
    sender_data = payload.get("senderData", {})

    msg = InboxMessage(
        instance_id=instance_id,
        sender_phone=sender_data.get("sender", "").replace("@c.us", "").replace("@g.us", ""),
        sender_name=sender_data.get("senderName", ""),
        message_type=data.get("typeMessage", "text"),
        text_content=data.get("textMessageData", {}).get("textMessage", ""),
        is_group="@g.us" in sender_data.get("chatId", ""),
        group_name=sender_data.get("chatName", ""),
        original_payload=json.dumps(payload, ensure_ascii=False),
        timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
    )

    async with AsyncSessionLocal() as db:
        db.add(msg)
        # Update received_today for the account
        from app.models.account import Account
        from sqlalchemy import select
        result = await db.execute(
            select(Account).where(Account.instance_id == instance_id)
        )
        account = result.scalar_one_or_none()
        if account:
            account.received_today += 1
        await db.commit()


async def _handle_state_change(instance_id: str, payload: dict):
    """Handle account state changes (banned, disconnected, etc.)."""
    state = payload.get("stateInstance", "")
    if state in ("blocked", "sleepMode"):
        from app.models.account import Account, AccountStatus
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Account).where(Account.instance_id == instance_id)
            )
            account = result.scalar_one_or_none()
            if account:
                account.status = AccountStatus.banned if state == "blocked" else AccountStatus.disconnected
                account.banned_at = datetime.utcnow()
                account.ban_reason = f"State changed to: {state}"
                await db.commit()
                print(f"[ALERT] Account {instance_id} status: {state}")


async def _handle_message_status(instance_id: str, payload: dict):
    """Update message delivery status."""
    msg_id = payload.get("idMessage", "")
    status = payload.get("status", "")
    if not msg_id:
        return

    from app.models.campaign import CampaignContact
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CampaignContact).where(
                CampaignContact.green_api_message_id == msg_id
            )
        )
        cc = result.scalar_one_or_none()
        if cc:
            # Update tick status
            cc.error_message = f"delivery: {status}"
            await db.commit()
