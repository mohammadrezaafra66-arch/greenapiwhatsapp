import asyncio, random, uuid, json
from datetime import datetime
from sqlalchemy import select, update
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus, CampaignType
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.services.gpt_service import generate_message, _apply_opening, _apply_opt_out
from app.services.price_service import get_products
from app.services.rate_limiter import can_send, record_send


async def fetch_campaign_products(campaign) -> list:
    """CRITICAL: fetch prices PER-MESSAGE (not per-campaign) so mid-campaign price changes
    are reflected immediately. get_products is Redis-cached (≤5 min) so this stays cheap.
    See V15 Item 24."""
    if getattr(campaign, "product_label_filter", None):
        from app.services.price_service import get_products_by_label
        return await get_products_by_label(campaign.product_label_filter, campaign.product_count)
    return await get_products(campaign.product_count)
from app.database import AsyncSessionLocal
from app.config import settings

# Auto-pause reasons surfaced in the campaign progress panel.
# V18 PART 1 — NO_ACCOUNT_REASON + fail-closed selection live in account_selection.
from app.services.account_selection import (
    NO_ACCOUNT_REASON, SELECTED_ACCOUNT_UNAVAILABLE_REASON, resolve_sending_accounts,
)
WINDOW_WAIT_REASON = "خارج از بازه مجاز ارسال این اکانت — ادامه خودکار در بازه بعدی"


async def build_message_text(campaign, contact, products, effective_gpt_prompt,
                             effective_template, effective_include_products) -> str:
    """Assemble the exact message text a contact would receive — the single source of
    truth shared by the runner and the /campaigns/preview endpoint (V13.6), so previews
    match real sends. `campaign`/`contact` need only attribute access (a real model or
    a SimpleNamespace)."""
    # Resolve opening line (random mode picks a fresh variant per contact).
    opening_mode = campaign.opening_mode or "ai"
    opening_line = campaign.opening_line
    if opening_mode == "random" and campaign.opening_variants:
        opening_line = random.choice(campaign.opening_variants)

    if campaign.use_gpt and settings.openai_api_key:
        message = await generate_message(
            first_name=contact.first_name or "",
            last_name=contact.last_name or "",
            gpt_prompt=effective_gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
            products=products if effective_include_products else None,
            emoji_level=campaign.emoji_level or "medium",
            show_prices=campaign.show_product_prices,
            opening_mode=opening_mode,
            opening_line=opening_line,
            include_opt_out=campaign.include_opt_out,
            opt_out_text=campaign.opt_out_text,
            use_rich_formatting=getattr(campaign, "use_rich_formatting", False),
            # V15 — group flag (Items 7/17/18) + product detail level (Item 8).
            is_group=(getattr(campaign, "campaign_scope", "pv") == "group"),
            product_detail_level=getattr(campaign, "product_detail_level", "medium"),
        )
    else:
        message = (effective_template or "سلام {{first_name}} جان!")
        message = message.replace("{{first_name}}", contact.first_name or "")
        message = message.replace("{{last_name}}", contact.last_name or "")
        # D6 — Persian variable aliases in templates
        message = message.replace("{نام}", contact.first_name or "")
        message = message.replace("{خانوادگی}", contact.last_name or "")
        message = message.replace("{شهر}", getattr(contact, "city", "") or "")
        message = message.replace("{استان}", getattr(contact, "province", "") or "")
        # V15 Item 18 — an empty {{name}} leaves a double space (e.g. «سلام  جان»); collapse it.
        while "  " in message:
            message = message.replace("  ", " ")
        message = "\n".join(l.rstrip() for l in message.split("\n"))
        # Honor opening + opt-out toggles on template messages too.
        message = _apply_opening(message, opening_mode, opening_line)
        message = _apply_opt_out(message, campaign.include_opt_out, campaign.opt_out_text)

    # Append seller signature if configured
    if campaign.append_seller_name and campaign.seller_name:
        message += f"\n\n👤 {campaign.seller_name}"
    if campaign.append_seller_phone and campaign.seller_phone:
        message += f"\n📱 {campaign.seller_phone}"
        if campaign.seller_phone2:
            message += f"\n☎️ {campaign.seller_phone2}"

    # Append Shamsi (Jalali) date if configured
    if campaign.append_date:
        try:
            import jdatetime
            message += f"\n\n📅 {jdatetime.date.today().strftime('%Y/%m/%d')}"
        except Exception:
            pass
    return message


async def _deliver_message(db, campaign, cc, contact, account, products, poll_options, buttons):
    """Generate + send one message for (cc, contact) using `account`; mutates state
    and commits. Returns the (possibly lazily-fetched) products list for reuse."""
    try:
        cc.status = MessageStatus.generating
        await db.commit()

        # Per-account per-hour override: if the account has a schedule for this
        # hour with a custom prompt/template/include_products, it takes precedence.
        from app.services.rate_limiter import get_hour_prompt_for_account
        hour_gpt_prompt, hour_template, hour_include_products = await get_hour_prompt_for_account(str(account.id))
        effective_gpt_prompt = hour_gpt_prompt or campaign.gpt_prompt
        effective_template = hour_template or campaign.message_template
        effective_include_products = campaign.include_products or hour_include_products
        # V13.1 — A/B test: variant B uses its own prompt/template when provided.
        if getattr(campaign, "ab_test_enabled", False) and getattr(cc, "ab_variant", None) == "B":
            effective_gpt_prompt = campaign.variant_b_prompt or effective_gpt_prompt
            effective_template = campaign.variant_b_template or effective_template
        # V15 Item 24 — fetch prices PER-MESSAGE (not the campaign-start snapshot) so a
        # price change mid-campaign is reflected on the very next message (cache ≤5 min).
        if effective_include_products:
            products = await fetch_campaign_products(campaign)

        # Build the message via the shared builder (same path the preview uses).
        message = await build_message_text(
            campaign, contact, products, effective_gpt_prompt, effective_template, effective_include_products
        )
        # V16 PART 3 — append advertising links (purely additive; '' when the toggle is off,
        # so a campaign with append_links=false produces byte-identical output to before).
        from app.services.adlinks import links_for_campaign
        message += await links_for_campaign(campaign, db)
        cc.generated_message = message
        client = GreenAPIClient(account.instance_id, account.api_token)

        # V17 PART 1 — typing indicator before sending. When the campaign's typing
        # simulation is OFF (default) this runs the EXACT V16 path (2–4s), so behavior
        # is byte-identical. When ON, it uses the length-scaled, jittered simulation.
        from app.services.typing_sim import show_typing_for_send
        await show_typing_for_send(
            client, contact.phone, message,
            enabled=getattr(campaign, "typing_simulation", False),
        )

        msg_id = None
        # V14 F7 — interactive buttons (opt-in, text campaigns only). Body = the built
        # message + a plain-text mirror of the reply choices so it still works if buttons
        # don't render. On a runtime 403, record UNSUPPORTED and re-send as plain text so
        # the recipient is NEVER skipped.
        if (getattr(campaign, "use_interactive_buttons", False) and campaign.buttons_config
                and campaign.campaign_type == CampaignType.text):
            from app.services.interactive import build_button_mirror, normalize_buttons
            from app.services.capabilities import is_supported, is_403, record_support
            body = message + build_button_mirror(campaign.buttons_config)
            if await is_supported(db, "sendInteractiveButtons") is not False:
                try:
                    msg_id = await client.send_interactive_buttons_rich(
                        contact.phone, campaign.button_header or "", body,
                        campaign.button_footer or "", normalize_buttons(campaign.buttons_config),
                    )
                    await record_support(db, "sendInteractiveButtons", True, 200)
                except Exception as e:
                    if is_403(e):
                        await record_support(db, "sendInteractiveButtons", False, 403,
                                             "runtime 403 → plain-text fallback")
                        msg_id = await client.send_message(contact.phone, body)  # never lose a send
                    else:
                        raise
            else:
                msg_id = await client.send_message(contact.phone, body)  # plan-restricted → plain text
        elif campaign.campaign_type == CampaignType.text:
            msg_id = await client.send_message(contact.phone, message)
        elif campaign.campaign_type == CampaignType.image and campaign.image_url:
            msg_id = await client.send_image(contact.phone, campaign.image_url, message)
        elif campaign.campaign_type == CampaignType.poll and campaign.poll_question:
            msg_id = await client.send_poll(contact.phone, campaign.poll_question, poll_options)
        elif campaign.campaign_type == CampaignType.interactive_buttons and buttons:
            msg_id = await client.send_interactive_buttons(contact.phone, message, buttons, campaign.footer_text or "")
        else:
            msg_id = await client.send_message(contact.phone, message)

        if msg_id:
            cc.status = MessageStatus.sent
            cc.sent_at = datetime.utcnow()
            cc.green_api_message_id = msg_id
            cc.account_id = account.id
            account.sent_today += 1
            campaign.sent_count += 1
            await record_send(str(account.id))
            # A3: also increment the scalable Redis day/hour counters (non-fatal).
            try:
                from app.services import redis_rate_limiter
                await redis_rate_limiter.record_send(str(account.id))
            except Exception:
                pass

            # Log to daily_send_logs for the night report
            from app.models.reporting import DailySendLog
            db.add(DailySendLog(
                account_id=account.id,
                account_name=account.name,
                campaign_name=campaign.name,
                recipient_phone=contact.phone,
                recipient_name=contact.full_name,
                status="sent",
            ))
        else:
            cc.status = MessageStatus.failed
            cc.error_message = "No message ID returned"
            campaign.failed_count += 1

    except Exception as e:
        cc.status = MessageStatus.failed
        cc.error_message = str(e)
        cc.retry_count += 1
        campaign.failed_count += 1
    finally:
        await db.commit()
    return products


async def run_campaign(campaign_id: str):
    """Single-run guard (B1.3/B1.4): only one instance processes a campaign at a
    time, so startup-resume and orphan-recovery re-queues can't double-send.
    Fail-open — if Redis is unavailable, run without the lock (current behavior)."""
    lock_key = f"campaign_lock:{campaign_id}"
    r = None
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        acquired = await r.set(lock_key, "1", nx=True, ex=14400)  # 4h TTL
        if not acquired:
            print(f"[Campaign {campaign_id}] already running (lock held) — skipping duplicate")
            return
    except Exception:
        r = None  # Redis down → proceed without a lock
    try:
        await _run_campaign_inner(campaign_id)
    finally:
        if r is not None:
            try:
                await r.delete(lock_key)
            except Exception:
                pass


async def _run_campaign_inner(campaign_id: str):
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign:
            return

        # Feature 35 — scheduled campaign window
        from app.utils.shamsi import to_shamsi
        now = datetime.utcnow()
        if campaign.schedule_end and now > campaign.schedule_end:
            campaign.status = CampaignStatus.completed
            campaign.completed_at = now
            await db.commit()
            return
        if campaign.schedule_start and now < campaign.schedule_start:
            # Not started yet — park and self-reschedule for the start time.
            wait = int((campaign.schedule_start - now).total_seconds())
            campaign.status = CampaignStatus.paused
            campaign.pause_reason = f"زمان شروع: {to_shamsi(campaign.schedule_start)}"
            await db.commit()
            try:
                from app.workers.tasks import task_run_campaign
                task_run_campaign.apply_async(args=[campaign_id], countdown=max(1, wait))
            except Exception as e:
                print(f"[Campaign {campaign_id}] schedule reschedule failed (non-fatal): {e}")
            return

        # Auto-resume a campaign that was parked waiting for the send window OR a
        # scheduled start time (this task was rescheduled for exactly that).
        if campaign.status == CampaignStatus.paused and (
            campaign.pause_reason == WINDOW_WAIT_REASON
            or (campaign.pause_reason or "").startswith("زمان شروع")
        ):
            campaign.status = CampaignStatus.running
            campaign.pause_reason = None
            await db.commit()
        if campaign.status != CampaignStatus.running:
            return

        result = await db.execute(
            select(CampaignContact, Contact)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status.in_([MessageStatus.pending])
            )
        )
        pending = result.all()
        if not pending:
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
            return

        accounts_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
        all_active = accounts_result.scalars().all()
        # V14 F23 — never send from an account resting in a yellowCard cooldown.
        # V18 PART 2 — nor from a number being mesh-warmed (active, not-yet-GRADUATED
        # warmup_enrollment); graduated numbers become eligible again.
        from app.services import governors
        from app.services.warmup_exclusion import enrollment_states_by_instance, warmup_campaign_excluded
        from app.services.listener_service import listener_campaign_excluded
        enr_map = await enrollment_states_by_instance(db)
        eligible = [a for a in all_active
                    if not governors.in_cooldown(a) and not warmup_campaign_excluded(a, enr_map)
                    and not listener_campaign_excluded(a)]
        # V18 PART 1 — FAIL-CLOSED selection. Selecting one account never expands to many;
        # if the chosen account is not eligible, ABORT (never fall back to all accounts).
        accounts, abort_reason = resolve_sending_accounts(eligible, campaign)
        if abort_reason:
            campaign.status = CampaignStatus.paused
            campaign.pause_reason = abort_reason
            await db.commit()
            return

        # Outside EVERY active account's send window (per-account hour schedule,
        # falling back to the global schedule) → auto-pause and self-reschedule
        # this task to fire when the earliest account window next opens.
        from app.services.rate_limiter import (
            get_max_per_hour_for_account, seconds_until_account_window,
        )
        acct_max = [await get_max_per_hour_for_account(str(a.id)) for a in accounts]
        if not any(m > 0 for m in acct_max):
            waits = [await seconds_until_account_window(str(a.id)) for a in accounts]
            positive = [w for w in waits if w > 0]
            wait_seconds = min(positive) if positive else 3600
            campaign.status = CampaignStatus.paused
            campaign.pause_reason = WINDOW_WAIT_REASON
            await db.commit()
            try:
                from app.workers.tasks import task_run_campaign
                task_run_campaign.apply_async(args=[campaign_id], countdown=wait_seconds)
                print(f"[Campaign {campaign_id}] outside all account windows — rescheduled in {wait_seconds}s")
            except Exception as e:
                print(f"[Campaign {campaign_id}] reschedule failed (non-fatal): {e}")
            return

        products = []
        if campaign.include_products:
            if campaign.product_label_filter:
                from app.services.price_service import get_products_by_label
                products = await get_products_by_label(campaign.product_label_filter, campaign.product_count)
            else:
                products = await get_products(campaign.product_count)

        poll_options = []
        if campaign.poll_options:
            try:
                poll_options = json.loads(campaign.poll_options)
            except Exception:
                poll_options = []

        buttons = [b for b in [campaign.button1_text, campaign.button2_text, campaign.button3_text] if b]

        # V13.2 — smart rotation: precompute per-account health scores once and pick
        # accounts weighted by health; falls back to round-robin when off/single account.
        health_scores = {}
        if getattr(campaign, "smart_rotation", False) and len(accounts) > 1:
            from app.services.account_health import account_health_score
            for a in accounts:
                try:
                    health_scores[str(a.id)] = await account_health_score(a, db)
                except Exception:
                    health_scores[str(a.id)] = 0.5

        # V13.8 — drip: cap this campaign's sends per Tehran-day; pause when the quota
        # is reached (the daily beat task resumes it the next day).
        drip_remaining = None
        drip_sent = 0
        if getattr(campaign, "drip_enabled", False):
            from app.services.drip import drip_count_today
            already = await drip_count_today(campaign_id)
            drip_remaining = max(0, (campaign.drip_per_day or 50) - already)

        acc_idx = 0
        for cc, contact in pending:
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break
            if drip_remaining is not None and drip_sent >= drip_remaining:
                from app.services.drip import PAUSE_REASON
                campaign.status = CampaignStatus.paused
                campaign.pause_reason = PAUSE_REASON
                await db.commit()
                return
            if contact.blacklisted or contact.has_whatsapp is False:
                cc.status = MessageStatus.skipped
                await db.commit()
                continue

            if health_scores:
                from app.services.account_health import pick_account_weighted
                account = pick_account_weighted(accounts, health_scores)
            else:
                account = accounts[acc_idx % len(accounts)]
                acc_idx += 1

            if account.sent_today >= governors.effective_daily_cap(account):
                continue
            if not await can_send(str(account.id)):
                await asyncio.sleep(60)
                continue

            # V14 F23.6 — warm-up new-contact cap (≤20 new/day for accounts <10 days).
            is_new_contact = getattr(contact, "first_messaged_at", None) is None
            if is_new_contact and not await governors.warmup_new_contact_allowed(str(account.id), account.days_active):
                continue

            products = await _deliver_message(db, campaign, cc, contact, account, products, poll_options, buttons)
            if cc.status == MessageStatus.sent and is_new_contact:
                contact.first_messaged_at = datetime.utcnow()
                await governors.record_new_contact(str(account.id))
                await db.commit()

            if drip_remaining is not None and cc.status == MessageStatus.sent:
                drip_sent += 1
                from app.services.drip import drip_incr
                await drip_incr(campaign_id)

            from app.services.delay_service import get_delay
            min_d, max_d = await get_delay(str(account.id))
            # V14 F23.6 — enforce the 500ms absolute floor between chats.
            delay = max(governors.MIN_DELAY_FLOOR_MS / 1000.0, random.uniform(min_d, max_d))
            await asyncio.sleep(delay)

        remaining = await db.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == MessageStatus.pending
            )
        )
        if not remaining.scalars().first():
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()


# ── Feature 37: parallel multi-account sending ─────────────────────────────
async def run_campaign_parallel(campaign_id: str, account_ids: list[str]):
    """Split pending contacts across the given accounts and send concurrently,
    one independent DB session + send loop per account."""
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign or campaign.status != CampaignStatus.running:
            return
        result = await db.execute(
            select(CampaignContact, Contact)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == MessageStatus.pending,
            )
        )
        pending = result.all()

    if not account_ids:
        await run_campaign(campaign_id)
        return
    if not pending:
        # Nothing to send → let the sequential path mark completion.
        await run_campaign(campaign_id)
        return

    # Round-robin split (store ids only — ORM objects are bound to the closed session).
    chunks = {aid: [] for aid in account_ids}
    for i, (cc, contact) in enumerate(pending):
        aid = account_ids[i % len(account_ids)]
        chunks[aid].append((str(cc.id), str(contact.id)))

    await asyncio.gather(
        *[_send_chunk(campaign_id, aid, items) for aid, items in chunks.items() if items],
        return_exceptions=True,
    )

    # Completion check
    async with AsyncSessionLocal() as db2:
        camp = await db2.get(Campaign, uuid.UUID(campaign_id))
        if not camp:
            return
        remaining = await db2.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == camp.id,
                CampaignContact.status == MessageStatus.pending,
            )
        )
        if not remaining.scalars().first():
            camp.status = CampaignStatus.completed
            camp.completed_at = datetime.utcnow()
            await db2.commit()


async def _send_chunk(campaign_id: str, account_id: str, items: list):
    """Send a chunk of (campaign_contact_id, contact_id) pairs using one fixed account."""
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        account = await db.get(Account, uuid.UUID(account_id))
        if not campaign or not account or account.status != AccountStatus.active:
            return

        products = []
        if campaign.include_products:
            if campaign.product_label_filter:
                from app.services.price_service import get_products_by_label
                products = await get_products_by_label(campaign.product_label_filter, campaign.product_count)
            else:
                products = await get_products(campaign.product_count)

        poll_options = []
        if campaign.poll_options:
            try:
                poll_options = json.loads(campaign.poll_options)
            except Exception:
                poll_options = []

        buttons = [b for b in [campaign.button1_text, campaign.button2_text, campaign.button3_text] if b]

        for cc_id, contact_id in items:
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break
            cc = await db.get(CampaignContact, uuid.UUID(cc_id))
            contact = await db.get(Contact, uuid.UUID(contact_id))
            if not cc or not contact or cc.status != MessageStatus.pending:
                continue
            if contact.blacklisted or contact.has_whatsapp is False:
                cc.status = MessageStatus.skipped
                await db.commit()
                continue
            from app.services import governors as _gov
            if account.sent_today >= _gov.effective_daily_cap(account):
                break  # this account has hit its daily cap
            if not await can_send(str(account.id)):
                await asyncio.sleep(60)
                continue

            products = await _deliver_message(db, campaign, cc, contact, account, products, poll_options, buttons)

            from app.services.delay_service import get_delay
            min_d, max_d = await get_delay(str(account.id))
            await asyncio.sleep(max(_gov.MIN_DELAY_FLOOR_MS / 1000.0, random.uniform(min_d, max_d)))
