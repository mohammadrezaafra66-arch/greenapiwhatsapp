import json
from datetime import datetime
from fastapi import APIRouter, Request, BackgroundTasks
from app.database import AsyncSessionLocal
from app.models.inbox import InboxMessage
from app.models.account import Account, AccountStatus
from app.models.campaign import CampaignContact
from sqlalchemy import select

router = APIRouter(prefix="/webhook", tags=["webhook"])

@router.post("/{instance_id}")
async def receive_webhook(instance_id: str, request: Request, bg: BackgroundTasks):
    body = await request.json()
    bg.add_task(process_webhook, instance_id, body)
    return {"status": "ok"}

async def process_webhook(instance_id: str, payload: dict):
    wtype = payload.get("typeWebhook", "")
    if wtype == "incomingMessageReceived":
        await handle_incoming(instance_id, payload)
    elif wtype == "stateInstanceChanged":
        await handle_state_change(instance_id, payload)
    elif wtype == "outgoingMessageStatus":
        await handle_outgoing_status(instance_id, payload)

async def handle_incoming(instance_id: str, payload: dict):
    data = payload.get("messageData", {})
    sender = payload.get("senderData", {})
    text = (
        data.get("textMessageData", {}).get("textMessage") or
        data.get("extendedTextMessageData", {}).get("text") or
        data.get("pollMessageData", {}).get("name") or ""
    )

    type_message = data.get("typeMessage", "text")
    is_edited = type_message == "editedMessage"
    is_deleted = type_message in ("deletedMessage", "revokedMessage")

    edited_text = None
    original_message_id = None
    if is_edited:
        edited_block = data.get("editedMessageData", {}) or {}
        edited_text = (
            edited_block.get("textMessageData", {}).get("textMessage")
            or edited_block.get("extendedTextMessageData", {}).get("text")
        )
        original_message_id = edited_block.get("stanzaId") or payload.get("idMessage")
        if edited_text:
            text = edited_text
    elif is_deleted:
        deleted_block = data.get("deletedMessageData", {}) or data.get("protocolMessageData", {}) or {}
        original_message_id = deleted_block.get("stanzaId") or payload.get("idMessage")

    from app.services.gpt_service import categorize_message
    from app.services.auto_reply import process_auto_reply
    from app.services.green_api import GreenAPIClient

    category = "other"
    if text:
        try:
            category = await categorize_message(text)
        except Exception:
            category = "other"
    sender_phone = sender.get("sender", "").split("@")[0]

    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type=data.get("typeMessage", "text"),
            text_content=text,
            is_group="@g.us" in sender.get("chatId", ""),
            group_name=sender.get("chatName", ""),
            category=category,
            original_payload=json.dumps(payload, ensure_ascii=False),
            is_deleted=is_deleted,
            edited_text=edited_text,
            original_message_id=original_message_id,
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)

        # Update account received count
        acc_result = await db.execute(select(Account).where(Account.instance_id == instance_id))
        account = acc_result.scalar_one_or_none()
        if account:
            account.received_today += 1

            # Check if auto-reply needed
            client = GreenAPIClient(account.instance_id, account.api_token)
            should_reply, reply_msg = await process_auto_reply(account, sender_phone, text, client)
            if should_reply and reply_msg and not msg.is_group:
                try:
                    await client.send_message(sender_phone, reply_msg)
                    msg.auto_replied = True
                except Exception:
                    pass

            # If unsubscribe → blacklist
            if text and text.strip() in ["11", "۱۱", "لغو"]:
                from app.models.inbox import Blacklist
                from app.models.contact import Contact
                bl_check = await db.execute(select(Blacklist).where(Blacklist.phone == sender_phone))
                if not bl_check.scalar_one_or_none():
                    bl = Blacklist(phone=sender_phone, reason="self_unsubscribed")
                    db.add(bl)
                contact_check = await db.execute(select(Contact).where(Contact.phone == sender_phone))
                ct = contact_check.scalar_one_or_none()
                if ct:
                    ct.blacklisted = True

        await db.commit()

async def handle_state_change(instance_id: str, payload: dict):
    state = payload.get("stateInstance", "")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Account).where(Account.instance_id == instance_id))
        account = result.scalar_one_or_none()
        if account:
            if state == "blocked":
                account.status = AccountStatus.banned
                account.banned_at = datetime.utcnow()
                account.ban_reason = "blocked by WhatsApp"
            elif state == "notAuthorized":
                account.status = AccountStatus.disconnected
            elif state == "authorized":
                account.status = AccountStatus.active
            await db.commit()

async def handle_outgoing_status(instance_id: str, payload: dict):
    msg_id = payload.get("idMessage", "")
    status = payload.get("status", "")
    if not msg_id or not status:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CampaignContact).where(CampaignContact.green_api_message_id == msg_id)
        )
        cc = result.scalar_one_or_none()
        if cc:
            cc.delivery_status = status
            from app.models.campaign import Campaign
            campaign = await db.get(Campaign, cc.campaign_id)
            if campaign:
                if status == "delivered":
                    campaign.delivered_count += 1
                elif status == "read":
                    campaign.read_count += 1
            await db.commit()
