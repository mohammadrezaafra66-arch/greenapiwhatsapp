import json
import logging
from datetime import datetime
from fastapi import APIRouter, Request, BackgroundTasks
from app.database import AsyncSessionLocal
from app.models.inbox import InboxMessage
from app.models.account import Account, AccountStatus
from app.models.campaign import CampaignContact
from sqlalchemy import select

logger = logging.getLogger("afrakala.webhook")
router = APIRouter(prefix="/webhook", tags=["webhook"])

@router.post("/{instance_id}")
async def receive_webhook(instance_id: str, request: Request, bg: BackgroundTasks):
    body = await request.json()
    bg.add_task(process_webhook, instance_id, body)
    return {"status": "ok"}


async def _already_processed(instance_id: str, id_message: str) -> bool:
    """B1.2 — webhook idempotency: Green API can deliver the same event twice.
    Mark idMessage as seen in Redis (24h TTL); return True if it was already
    seen. Fail-open: if Redis is unavailable, never block processing."""
    if not id_message:
        return False
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        # SET NX returns True only the first time → not-first means duplicate.
        first = await r.set(f"webhook_seen:{instance_id}:{id_message}", "1", nx=True, ex=86400)
        return not first
    except Exception:
        return False


async def process_webhook(instance_id: str, payload: dict):
    wtype = payload.get("typeWebhook", "")

    # B1.2 — skip duplicate deliveries (only events carrying an idMessage).
    if await _already_processed(instance_id, payload.get("idMessage", "")):
        return

    # B1.6 — isolate handlers: one malformed webhook must not crash the loop.
    try:
        if wtype == "incomingMessageReceived":
            await handle_incoming(instance_id, payload)
        elif wtype == "stateInstanceChanged":
            await handle_state_change(instance_id, payload)
        elif wtype == "outgoingMessageStatus":
            await handle_outgoing_status(instance_id, payload)
        elif wtype == "incomingCall":
            await handle_incoming_call(instance_id, payload)
        elif wtype == "buttonsResponseMessage":
            await handle_button_reply(instance_id, payload)
        elif wtype == "pollUpdateMessage":
            await handle_poll_update(instance_id, payload)
        elif wtype == "quotaExceeded":
            await handle_quota_exceeded(instance_id, payload)
        elif wtype in ("deviceStatusChanged", "deviceWebhook"):
            await handle_device_status(instance_id, payload)
        elif wtype in ("statusInstanceChanged", "statusInstance"):
            pass  # Already handled by handle_state_change — skip duplicate
        elif wtype in ("catalogUpdate", "catalogWebhook"):
            await handle_catalog_update(instance_id, payload)
        elif wtype in ("incomingBlock", "incomingChatBlock"):
            await handle_incoming_block(instance_id, payload)
        elif wtype in ("outgoingCall", "outgoingCallReceived"):
            await handle_outgoing_call(instance_id, payload)
    except Exception as e:
        logger.warning("webhook handler failed (type=%s, instance=%s): %s", wtype, instance_id, e)

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

            # V13.4 — auto opt-out on keyword reply (configurable, digit-normalized)
            from app.services.optout import is_opt_out
            if is_opt_out(text):
                from app.models.inbox import Blacklist
                from app.models.contact import Contact
                from app.models.optout import OptOutLog
                bl_check = await db.execute(select(Blacklist).where(Blacklist.phone == sender_phone))
                if not bl_check.scalar_one_or_none():
                    db.add(Blacklist(phone=sender_phone, reason="self_unsubscribed"))
                contact_check = await db.execute(select(Contact).where(Contact.phone == sender_phone))
                ct = contact_check.scalar_one_or_none()
                if ct:
                    ct.blacklisted = True
                db.add(OptOutLog(phone=sender_phone, reason="opt_out_keyword"))

            # Keyword auto-reply (runs even if auto_reply already fired — both can reply)
            if text and not msg.is_group or text:
                try:
                    from app.services.keyword_service import check_keywords, increment_use_count
                    kw_matched, kw_reply, kw_rule_id, rule_scope = await check_keywords(
                        instance_id=instance_id,
                        message_text=text,
                        is_group=msg.is_group,
                        account_id=str(account.id) if account else None,
                    )
                    if kw_matched and kw_reply and account:
                        # scope determines WHERE to reply: 'group'/'both' in a group
                        # replies to the group chatId (raw), otherwise to the sender (PV).
                        if rule_scope in ("group", "both") and msg.is_group:
                            group_chat_id = sender.get("chatId", "")
                            if group_chat_id:
                                await client.send_group_message(group_chat_id, kw_reply)
                            else:
                                await client.send_message(sender_phone, kw_reply)
                        else:
                            await client.send_message(sender_phone, kw_reply)
                        if kw_rule_id:
                            await increment_use_count(kw_rule_id)
                except Exception as e:
                    print(f"[Keyword] match/reply failed (non-fatal): {e}")

        # Product mention detection (only in groups). Token-based matching:
        # a brand keyword + a capacity/model token (see product_match).
        if msg.is_group and text:
            try:
                from app.services.price_service import get_products
                from app.services.product_match import match_products
                from app.models.reporting import ProductMentionLog
                products = await get_products(200)  # get all products
                hits = match_products(text, products)
                if hits:
                    async with AsyncSessionLocal() as log_db:
                        log_db.add(ProductMentionLog(
                            product_name=hits[0],  # one mention per message
                            sender_phone=sender_phone,
                            sender_name=sender.get("senderName", ""),
                            group_name=sender.get("chatName", ""),
                            group_chat_id=sender.get("chatId", ""),
                            instance_id=instance_id,
                            message_text=text[:500],
                        ))
                        await log_db.commit()
            except Exception as e:
                logger.warning("[ProductMention] detection error: %s", e)

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


async def handle_incoming_call(instance_id: str, payload: dict):
    """Log incoming WhatsApp calls."""
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="call",
            call_status=payload.get("status", "missed"),
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)
        await db.commit()


async def handle_button_reply(instance_id: str, payload: dict):
    """Handle interactive button reply from a recipient."""
    data = payload.get("messageData", {})
    button_data = data.get("buttonsResponseMessage", {})
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]

    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="button_reply",
            text_content=button_data.get("selectedDisplayText", ""),
            button_reply_id=button_data.get("selectedButtonId", ""),
            button_reply_title=button_data.get("selectedDisplayText", ""),
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)

        # Track campaign reply count
        from app.models.campaign import CampaignContact
        from sqlalchemy import select as sa_select
        result = await db.execute(
            sa_select(CampaignContact).where(
                CampaignContact.status.in_(["sent"]),
            ).limit(1)
        )
        await db.commit()


async def handle_poll_update(instance_id: str, payload: dict):
    """Handle poll vote update — store votes in inbox."""
    import json as _json
    data = payload.get("messageData", {})
    poll_data = data.get("pollMessageData", {})
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]

    votes = poll_data.get("votes", [])

    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="poll_update",
            poll_votes=_json.dumps(votes, ensure_ascii=False),
            original_payload=_json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)

        # Update campaign reply/poll stats
        from app.models.campaign import Campaign
        from sqlalchemy import select as sa_select, update as sa_update
        await db.commit()


async def handle_quota_exceeded(instance_id: str, payload: dict):
    """Mark account as quota-exceeded when Green API signals limit hit."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Account).where(Account.instance_id == instance_id)
        )
        account = result.scalar_one_or_none()
        if account:
            account.quota_exceeded_at = datetime.utcnow()
            # Don't ban — quota resets, unlike a real ban
            await db.commit()
            print(f"[ALERT] Account {instance_id} quota exceeded at {datetime.utcnow()}")


async def handle_device_status(instance_id: str, payload: dict):
    """Handle device status changes (battery, online status, etc.)."""
    device_status = payload.get("deviceStatus", {}) or payload.get("status", "")
    print(f"[Device] instance {instance_id} device status: {device_status}")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Account).where(Account.instance_id == instance_id))
        account = result.scalar_one_or_none()
        if account:
            account.notes = f"[device] {device_status} at {datetime.utcnow().isoformat()}"
            await db.commit()


async def handle_catalog_update(instance_id: str, payload: dict):
    """Handle WhatsApp catalog updates — store as inbox message."""
    sender = payload.get("senderData", {})
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender.get("sender", "").split("@")[0],
            sender_name=sender.get("senderName", ""),
            message_type="catalog_update",
            text_content="آپدیت کاتالوگ",
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0) or 0)
        )
        db.add(msg)
        await db.commit()


async def handle_incoming_block(instance_id: str, payload: dict):
    """Handle when someone blocks this WhatsApp number — auto-blacklist them."""
    sender = payload.get("senderData", {})
    blocker_phone = sender.get("sender", "").split("@")[0]
    print(f"[ALERT] Blocked by {blocker_phone} on instance {instance_id}")
    async with AsyncSessionLocal() as db:
        from app.models.inbox import Blacklist
        from sqlalchemy import select as sa_select
        existing = await db.execute(sa_select(Blacklist).where(Blacklist.phone == blocker_phone))
        if not existing.scalar_one_or_none():
            db.add(Blacklist(phone=blocker_phone, reason="blocked_us"))
        from app.models.contact import Contact
        contact_result = await db.execute(sa_select(Contact).where(Contact.phone == blocker_phone))
        ct = contact_result.scalar_one_or_none()
        if ct:
            ct.blacklisted = True
            ct.blacklist_reason = "blocked_this_number"
        # V13.4 — record the auto opt-out reason
        from app.models.optout import OptOutLog
        db.add(OptOutLog(phone=blocker_phone, reason="blocked"))
        await db.commit()


async def handle_outgoing_call(instance_id: str, payload: dict):
    """Log outgoing calls to inbox for tracking."""
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=payload.get("from", "").split("@")[0],
            message_type="outgoing_call",
            call_status=payload.get("status", "outgoing"),
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0) or 0)
        )
        db.add(msg)
        await db.commit()
