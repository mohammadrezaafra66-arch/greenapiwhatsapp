"""
Runs a group-scope campaign: sends the campaign message to each configured
WhatsApp group on the scheduled interval. Respects per-account rate limits.
"""
import asyncio, random, json, uuid
from datetime import datetime
from sqlalchemy import select
from app.models.campaign import Campaign, CampaignStatus
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from app.services.gpt_service import generate_message
from app.services.price_service import get_products
from app.services.rate_limiter import can_send, record_send
from app.services.delay_service import get_delay
from app.database import AsyncSessionLocal
from app.config import settings


async def run_group_campaign(campaign_id: str):
    """Send campaign message to every group_id in the campaign."""
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign or campaign.status != CampaignStatus.running:
            return
        if not campaign.group_ids:
            campaign.status = CampaignStatus.completed
            await db.commit()
            return

        try:
            group_ids = json.loads(campaign.group_ids)
        except Exception:
            campaign.status = CampaignStatus.completed
            await db.commit()
            return

        accounts_result = await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )
        accounts = accounts_result.scalars().all()
        if not accounts:
            return

        products = []
        if campaign.include_products:
            products = await get_products(campaign.product_count)

        acc_idx = 0
        for group_id in group_ids:
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break

            account = accounts[acc_idx % len(accounts)]
            acc_idx += 1

            if not await can_send(str(account.id)):
                await asyncio.sleep(60)
                continue

            try:
                if campaign.use_gpt and settings.openai_api_key:
                    message = await generate_message(
                        first_name="گروه",
                        last_name="",
                        gpt_prompt=campaign.gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
                        products=products if campaign.include_products else None
                    )
                else:
                    message = campaign.message_template or "پیام افراکالا"

                client = GreenAPIClient(account.instance_id, account.api_token)

                # Show "typing..." for 2-4 seconds before sending (more human-like)
                try:
                    typing_secs = random.randint(2, 4)
                    await client.send_typing(group_id, typing_secs)
                    await asyncio.sleep(typing_secs)
                except Exception:
                    pass  # Non-fatal — never block sending

                if campaign.campaign_type and campaign.campaign_type.value == "image" and campaign.image_url:
                    msg_id = await client.send_image(group_id, campaign.image_url, message)
                else:
                    msg_id = await client.send_group_message(group_id, message)

                if msg_id:
                    campaign.sent_count += 1
                    account.sent_today += 1
                    await record_send(str(account.id))
                else:
                    campaign.failed_count += 1

            except Exception as e:
                campaign.failed_count += 1
                print(f"[GroupCampaign] group {group_id} error: {e}")
            finally:
                await db.commit()

            min_d, max_d = await get_delay(str(account.id))
            await asyncio.sleep(random.uniform(min_d, max_d))

        campaign.status = CampaignStatus.completed
        campaign.completed_at = datetime.utcnow()
        await db.commit()
