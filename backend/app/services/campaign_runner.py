import asyncio, random, uuid, json
from datetime import datetime
from sqlalchemy import select, update
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus, CampaignType
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.services.gpt_service import generate_message
from app.services.price_service import get_products
from app.services.rate_limiter import can_send, record_send
from app.database import AsyncSessionLocal
from app.config import settings

# Auto-pause reasons surfaced in the campaign progress panel.
NO_ACCOUNT_REASON = "هیچ اکانت فعالی متصل نیست — کمپین به‌طور خودکار متوقف شد"
WINDOW_WAIT_REASON = "خارج از بازه مجاز ارسال (۸ تا ۲۲ به وقت تهران) — ادامه خودکار در ۰۸:۰۰"


async def run_campaign(campaign_id: str):
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign:
            return
        # Auto-resume a campaign that was parked waiting for the send window to
        # open (this task was rescheduled via eta/countdown for exactly that).
        if campaign.status == CampaignStatus.paused and campaign.pause_reason == WINDOW_WAIT_REASON:
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
        accounts = accounts_result.scalars().all()
        if not accounts:
            # No connected account to send with → auto-pause with a clear reason.
            campaign.status = CampaignStatus.paused
            campaign.pause_reason = NO_ACCOUNT_REASON
            await db.commit()
            return

        # Outside the daily send window → auto-pause and self-reschedule this task
        # to fire when the window next opens (08:00 Tehran).
        from app.services.rate_limiter import seconds_until_send_window
        wait_seconds = seconds_until_send_window()
        if wait_seconds > 0:
            campaign.status = CampaignStatus.paused
            campaign.pause_reason = WINDOW_WAIT_REASON
            await db.commit()
            try:
                from app.workers.tasks import task_run_campaign
                task_run_campaign.apply_async(args=[campaign_id], countdown=wait_seconds)
                print(f"[Campaign {campaign_id}] outside send window — rescheduled in {wait_seconds}s")
            except Exception as e:
                print(f"[Campaign {campaign_id}] reschedule failed (non-fatal): {e}")
            return

        products = []
        if campaign.include_products:
            products = await get_products(campaign.product_count)

        poll_options = []
        if campaign.poll_options:
            try:
                poll_options = json.loads(campaign.poll_options)
            except Exception:
                poll_options = []

        buttons = [b for b in [campaign.button1_text, campaign.button2_text, campaign.button3_text] if b]

        acc_idx = 0
        for cc, contact in pending:
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break
            if contact.blacklisted or contact.has_whatsapp is False:
                cc.status = MessageStatus.skipped
                await db.commit()
                continue

            account = accounts[acc_idx % len(accounts)]
            acc_idx += 1

            if account.sent_today >= account.computed_daily_limit:
                continue
            if not await can_send(str(account.id)):
                await asyncio.sleep(60)
                continue

            try:
                cc.status = MessageStatus.generating
                await db.commit()

                # Per-account per-hour override: if the account has a schedule for this
                # hour with a custom prompt/template, it takes precedence.
                from app.services.rate_limiter import get_hour_prompt_for_account
                hour_gpt_prompt, hour_template = await get_hour_prompt_for_account(str(account.id))
                effective_gpt_prompt = hour_gpt_prompt or campaign.gpt_prompt
                effective_template = hour_template or campaign.message_template

                # Generate message text
                if campaign.use_gpt and settings.openai_api_key:
                    message = await generate_message(
                        first_name=contact.first_name or "",
                        last_name=contact.last_name or "",
                        gpt_prompt=effective_gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
                        products=products if campaign.include_products else None
                    )
                else:
                    message = (effective_template or "سلام {{first_name}} جان!")
                    message = message.replace("{{first_name}}", contact.first_name or "")
                    message = message.replace("{{last_name}}", contact.last_name or "")

                cc.generated_message = message
                client = GreenAPIClient(account.instance_id, account.api_token)

                # Show "typing..." for 2-4 seconds before sending (more human-like)
                try:
                    typing_secs = random.randint(2, 4)
                    await client.send_typing(contact.phone, typing_secs)
                    await asyncio.sleep(typing_secs)
                except Exception:
                    pass  # Non-fatal — never block sending

                msg_id = None

                # Send based on campaign type
                if campaign.campaign_type == CampaignType.text:
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

            from app.services.delay_service import get_delay
            min_d, max_d = await get_delay(str(account.id))
            delay = random.uniform(min_d, max_d)
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
