"""
Campaign runner: manages the lifecycle of a campaign's message sending.
Respects rate limits, daily account limits, and human-like delays.
"""
import asyncio
import random
import json
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.services.gpt_service import generate_message
from app.services.price_service import get_products
from app.services.rate_limiter import can_send_now, record_send
from app.database import AsyncSessionLocal
from app.config import settings


async def run_campaign(campaign_id: str):
    """Main campaign runner — called by Celery task."""
    async with AsyncSessionLocal() as db:
        # Get campaign
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign or campaign.status != CampaignStatus.running:
            return

        # Get pending messages
        result = await db.execute(
            select(CampaignContact, Contact, Account)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .outerjoin(Account, CampaignContact.account_id == Account.id)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status.in_([MessageStatus.pending, MessageStatus.queued])
            )
        )
        pending = result.all()

        if not pending:
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
            return

        # Get available accounts
        accounts_result = await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )
        accounts = accounts_result.scalars().all()
        if not accounts:
            return

        # Get products if needed
        products = []
        if campaign.include_products:
            products = await get_products(campaign.product_count)

        account_idx = 0
        for cc, contact, _ in pending:
            # Check if campaign is still running
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break

            # Pick account round-robin
            account = accounts[account_idx % len(accounts)]
            account_idx += 1

            # Check daily limit
            if account.sent_today >= account.computed_daily_limit:
                continue

            # Check hourly rate limit
            if not await can_send_now(str(account.id)):
                await asyncio.sleep(60)  # Wait 1 minute and try again
                continue

            # Skip blacklisted contacts
            if contact.blacklisted or contact.has_whatsapp is False:
                cc.status = MessageStatus.skipped
                await db.commit()
                continue

            # Generate message
            try:
                cc.status = MessageStatus.generating
                await db.commit()

                if campaign.use_gpt and settings.openai_api_key:
                    message = await generate_message(
                        first_name=contact.first_name or "",
                        last_name=contact.last_name or "",
                        gpt_prompt=campaign.gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
                        products=products if campaign.include_products else None
                    )
                else:
                    # Use template with variable substitution
                    template = campaign.message_template or "سلام {{first_name}} جان، از افراکالا پیامی داریم."
                    message = template.replace("{{first_name}}", contact.first_name or "")
                    message = message.replace("{{last_name}}", contact.last_name or "")

                cc.generated_message = message

                # Send via Green API
                client = GreenAPIClient(account.instance_id, account.api_token)

                if campaign.send_image and campaign.image_url:
                    msg_id = await client.send_image(contact.phone, campaign.image_url, message)
                else:
                    msg_id = await client.send_message(contact.phone, message)

                if msg_id:
                    cc.status = MessageStatus.sent
                    cc.sent_at = datetime.utcnow()
                    cc.green_api_message_id = msg_id
                    cc.account_id = account.id

                    # Update counters
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

            # Human-like delay
            delay = random.uniform(settings.default_min_delay, settings.default_max_delay)
            await asyncio.sleep(delay)

        # Check if all done
        remaining = await db.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status.in_([MessageStatus.pending, MessageStatus.queued])
            )
        )
        if not remaining.scalars().first():
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
