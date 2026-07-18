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

    # V14 F8/F11 — interactive button replies and reactions arrive as
    # incomingMessageReceived. Handle and return before the normal text pipeline.
    if type_message in ("interactiveButtons", "interactiveButtonsReply") \
            or data.get("interactiveButtonsReply") or data.get("interactiveButtons"):
        await _process_button_reply(instance_id, payload)
        return
    if type_message == "reactionMessage" or data.get("reactionMessage"):
        await _process_reaction(instance_id, payload)
        return

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

        # V14 F9 — confirm an edit of one of OUR sent messages: mark the campaign
        # contact is_edited (the editedMessage webhook carries the original stanzaId).
        if is_edited and original_message_id:
            _cc_edit = (await db.execute(
                select(CampaignContact).where(
                    CampaignContact.green_api_message_id == original_message_id)
            )).scalar_one_or_none()
            if _cc_edit:
                _cc_edit.is_edited = True
                _cc_edit.edited_at = datetime.utcnow()
                if edited_text:
                    _cc_edit.generated_message = edited_text

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

            # V13.7 — mark the most recent campaign_contact for this phone as replied
            # (best-effort match by phone + recency, group messages excluded).
            if text and not msg.is_group:
                from datetime import timedelta
                from app.models.contact import Contact as _Contact
                _ct = (await db.execute(select(_Contact).where(_Contact.phone == sender_phone))).scalar_one_or_none()
                if _ct:
                    recent = datetime.utcnow() - timedelta(days=14)
                    _cc = (await db.execute(
                        select(CampaignContact).where(
                            CampaignContact.contact_id == _ct.id,
                            CampaignContact.sent_at.isnot(None),
                            CampaignContact.sent_at >= recent,
                        ).order_by(CampaignContact.sent_at.desc()).limit(1)
                    )).scalar_one_or_none()
                    if _cc and not _cc.replied:
                        _cc.replied = True

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
                    # V27 PART 1 — live pre-send health gate on the auto-reply send path.
                    from app.services.send_gate import gate_check as _gate_check
                    _kw_allowed = bool(account) and _gate_check(account)[0]
                    if kw_matched and kw_reply and account and _kw_allowed:
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

        # V25 PART 1 — human-helper warm-up assist: if this cold number just received an
        # incoming message from a known helper's phone, mark the helper's task done and
        # auto-thank them. PV only; guarded & best-effort so it can never disrupt the webhook.
        if not msg.is_group and sender_phone:
            try:
                from app.services.warmup_helper_engine import handle_helper_incoming
                await handle_helper_incoming(db, instance_id, sender_phone, datetime.utcnow())
            except Exception as e:
                logger.warning("helper warm-up detection failed (non-fatal): %s", e)

        await db.commit()

async def handle_state_change(instance_id: str, payload: dict):
    state = payload.get("stateInstance", "")
    # V27 PART 4 — a pushed state-change webhook updates the gate's live-state mirror
    # IMMEDIATELY (faster than the ~60s poll), so a just-carded instance is refused by the
    # pre-send gate within a webhook round-trip rather than sending more messages.
    from app.services import send_gate
    send_gate.update_live_state(instance_id, state)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Account).where(Account.instance_id == instance_id))
        account = result.scalar_one_or_none()
        if account:
            await send_gate.persist_live_state(db, instance_id, state, "webhook")
            if state == "blocked":
                account.status = AccountStatus.banned
                account.banned_at = datetime.utcnow()
                account.ban_reason = "blocked by WhatsApp"
                await db.commit()
            elif state == "notAuthorized":
                account.status = AccountStatus.disconnected
                await db.commit()
            elif state == "authorized":
                account.status = AccountStatus.active
                await db.commit()
            elif state == "yellowCard":
                # V14 F23 — automatic incident response (commits internally).
                from app.services.incident_handler import handle_yellow_card
                await handle_yellow_card(account, "webhook", db)
            else:
                await db.commit()
    # V17 PART 5 — route the state signal into the mesh warm-up kill-switch (pause/rest on
    # yellowCard, reset on block/logout, restart on re-auth, chain-ban breaker). Guarded &
    # best-effort so it can never disrupt the fragile webhook path. No-op if not enrolled.
    try:
        from app.services.warmup_killswitch import handle_warmup_state_signal
        async with AsyncSessionLocal() as wdb:
            if await handle_warmup_state_signal(wdb, instance_id, state) is not None:
                await wdb.commit()
    except Exception as e:
        logger.warning("warmup state signal failed (non-fatal): %s", e)

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
            if status == "yellowCard":
                # V14 F23 — a yellowCard can also surface on an outgoing status.
                acc = (await db.execute(
                    select(Account).where(Account.instance_id == instance_id)
                )).scalar_one_or_none()
                if acc:
                    from app.services.incident_handler import handle_yellow_card
                    await handle_yellow_card(acc, "messageStatus", db)
            # V14 F9 — a silent edit failure (Green API returned 200 but WhatsApp rejected
            # it) arrives as status=failed with a descriptive reason.
            if status == "failed":
                desc = payload.get("description") or payload.get("sendByApi") or ""
                if desc:
                    cc.error_message = str(desc)[:500]
            from app.models.campaign import Campaign
            campaign = await db.get(Campaign, cc.campaign_id)
            if campaign:
                if status == "delivered":
                    campaign.delivered_count += 1
                elif status == "read":
                    campaign.read_count += 1
            await db.commit()


async def handle_incoming_call(instance_id: str, payload: dict):
    """Log incoming WhatsApp calls (also to call_logs — F24)."""
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]
    status = payload.get("status", "missed")
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="call",
            call_status=status,
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0))
        )
        db.add(msg)
        acc = (await db.execute(select(Account).where(Account.instance_id == instance_id))).scalar_one_or_none()
        from app.models.incident import CallLog
        db.add(CallLog(
            account_id=acc.id if acc else None, direction="incoming",
            from_phone=sender_phone, status=status, contact_name=sender.get("senderName", ""),
            called_at=datetime.fromtimestamp(payload.get("timestamp", 0) or 0),
        ))
        await db.commit()


async def handle_button_reply(instance_id: str, payload: dict):
    """Legacy buttonsResponseMessage webhook → shared handler."""
    await _process_button_reply(instance_id, payload)


async def _process_button_reply(instance_id: str, payload: dict):
    """FEATURE 8 — record a pressed interactive button, mark the campaign contact as
    replied (feeds the V13.7 ROI funnel), and fire any matching auto-reply rule.
    Tolerant of all webhook shapes (parse_button_reply never raises)."""
    from app.services.interactive import parse_button_reply
    from app.models.messaging import ButtonReply, ButtonAutoReply
    from app.models.contact import Contact
    from app.services.green_api import GreenAPIClient
    from datetime import timedelta

    parsed = parse_button_reply(payload)
    if not parsed:
        return
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]
    chat_id = sender.get("chatId", "")

    async with AsyncSessionLocal() as db:
        # Inbox thread entry
        db.add(InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="button_reply",
            text_content=parsed["button_text"],
            button_reply_id=parsed["button_id"],
            button_reply_title=parsed["button_text"],
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0) or 0),
        ))

        campaign_id = None
        # Best-effort: match sender → most recent sent campaign_contact → replied=true
        ct = (await db.execute(select(Contact).where(Contact.phone == sender_phone))).scalar_one_or_none()
        if ct:
            recent = datetime.utcnow() - timedelta(days=14)
            cc = (await db.execute(
                select(CampaignContact).where(
                    CampaignContact.contact_id == ct.id,
                    CampaignContact.sent_at.isnot(None),
                    CampaignContact.sent_at >= recent,
                ).order_by(CampaignContact.sent_at.desc()).limit(1)
            )).scalar_one_or_none()
            if cc:
                campaign_id = cc.campaign_id
                if not cc.replied:
                    cc.replied = True

        db.add(ButtonReply(
            campaign_id=campaign_id,
            contact_phone=sender_phone,
            chat_id=chat_id,
            button_id=parsed["button_id"],
            button_text=parsed["button_text"],
            message_id=parsed["message_id"],
        ))

        # Auto-reply: match by button_id OR exact button_text (enabled rules only).
        rule = (await db.execute(
            select(ButtonAutoReply).where(
                ButtonAutoReply.enabled.is_(True),
                (ButtonAutoReply.button_id == parsed["button_id"])
                | (ButtonAutoReply.button_text == parsed["button_text"]),
            ).limit(1)
        )).scalar_one_or_none()
        if rule and rule.reply_text:
            acc = (await db.execute(select(Account).where(Account.instance_id == instance_id))).scalar_one_or_none()
            if acc:
                try:
                    await GreenAPIClient(acc.instance_id, acc.api_token).send_message(sender_phone, rule.reply_text)
                except Exception as e:
                    logger.warning("button auto-reply send failed: %s", e)

        await db.commit()


async def _process_reaction(instance_id: str, payload: dict):
    """FEATURE 11 (receive) — store an incoming emoji reaction and surface it in the
    Inbox thread. Send-reaction is NOT shipped (probe = 403)."""
    from app.services.interactive import parse_reaction
    from app.models.messaging import MessageReaction

    parsed = parse_reaction(payload)
    if not parsed:
        return
    sender = payload.get("senderData", {})
    sender_phone = sender.get("sender", "").split("@")[0]
    chat_id = sender.get("chatId", "")

    async with AsyncSessionLocal() as db:
        db.add(MessageReaction(
            chat_id=chat_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            emoji=parsed["emoji"],
            reacted_message_id=parsed["reacted_message_id"],
        ))
        # Also surface inline in the inbox thread.
        db.add(InboxMessage(
            instance_id=instance_id,
            sender_phone=sender_phone,
            sender_name=sender.get("senderName", ""),
            message_type="reaction",
            text_content=parsed["emoji"],
            original_message_id=parsed["reacted_message_id"],
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0) or 0),
        ))
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
            # V27 PART 10 — record a DISTINCT tariff/quota alert (not a ban/yellowCard) so the
            # admin knows the cause is billing, not health. Sets quota_exceeded_at internally.
            from app.services.quota_monitor import record_quota_incident
            await record_quota_incident(db, account, via="webhook")
            await db.commit()
            print(f"[ALERT] Account {instance_id} tariff/quota exceeded at {datetime.utcnow()}")


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

        # V14 F23.6 — post-complaint quiet period: ≥3 blocks in 24h for one account →
        # auto-throttle 0.5 for 10 days (warning-severity incident, no cooldown).
        try:
            from app.services import redis_rate_limiter
            r = await redis_rate_limiter.get_redis()
            key = f"blocks24h:{instance_id}"
            n = await r.incr(key)
            if n == 1:
                await r.expire(key, 86400)
            if n == 3:
                acc = (await db.execute(select(Account).where(Account.instance_id == instance_id))).scalar_one_or_none()
                if acc:
                    from app.services.incident_handler import apply_warning_throttle
                    await apply_warning_throttle(acc, "blockSpike", "webhook", db, factor=0.5, days=10)
        except Exception as e:
            logger.warning("block-spike check failed: %s", e)

        # V17 PART 5 — if this number is in mesh warm-up, log a block incident and let the
        # chain-ban breaker decide whether to halt the whole mesh. Guarded & best-effort.
        try:
            from app.models.warmup_mesh import WarmupEnrollment
            from app.services.warmup_killswitch import record_incident, check_and_maybe_trip_breaker
            enr = (await db.execute(
                select(WarmupEnrollment).where(WarmupEnrollment.instance_id == instance_id)
            )).scalar_one_or_none()
            if enr:
                await record_incident(db, instance_id, "block")
                await check_and_maybe_trip_breaker(db)
                await db.commit()
        except Exception as e:
            logger.warning("warmup block incident failed (non-fatal): %s", e)


async def handle_outgoing_call(instance_id: str, payload: dict):
    """Log outgoing calls to inbox + call_logs (F24)."""
    from_phone = payload.get("from", "").split("@")[0]
    status = payload.get("status", "outgoing")
    async with AsyncSessionLocal() as db:
        msg = InboxMessage(
            instance_id=instance_id,
            sender_phone=from_phone,
            message_type="outgoing_call",
            call_status=status,
            original_payload=json.dumps(payload, ensure_ascii=False),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", 0) or 0)
        )
        db.add(msg)
        acc = (await db.execute(select(Account).where(Account.instance_id == instance_id))).scalar_one_or_none()
        from app.models.incident import CallLog
        db.add(CallLog(
            account_id=acc.id if acc else None, direction="outgoing",
            from_phone=from_phone, status=status,
            called_at=datetime.fromtimestamp(payload.get("timestamp", 0) or 0),
        ))
        await db.commit()
