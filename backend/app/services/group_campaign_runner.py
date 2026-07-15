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
from app.services.gpt_service import generate_message, _apply_opening, _apply_opt_out
from app.services.price_service import get_products
from app.services.product_selection import select_group_products
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
        all_active = accounts_result.scalars().all()
        # V18 PART 1 — same fail-closed selection as PV campaigns: exclude cooldown/warming
        # accounts, then honor the user's explicit selection; never fan out to all accounts
        # when a chosen account is unavailable.
        from app.services import governors
        from app.services.warmup_auto import in_active_warmup
        from app.services.account_selection import resolve_sending_accounts
        eligible = [a for a in all_active if not governors.in_cooldown(a) and not in_active_warmup(a)]
        accounts, abort_reason = resolve_sending_accounts(eligible, campaign)
        if abort_reason:
            campaign.status = CampaignStatus.paused
            campaign.pause_reason = abort_reason
            await db.commit()
            return

        # Product POOL. For per-group variation we need more products than we show
        # per group, so each group can get a different slice/subset.
        variation = campaign.product_variation_mode or "same"
        per_group = campaign.products_per_group or campaign.product_count or 3
        weights = campaign.product_weights or {}
        pool_size = per_group if variation == "same" else max(per_group * 4, 15, campaign.product_count or 0)

        opening_mode = campaign.opening_mode or "ai"

        # V15 Item 22 — track products used across groups so per_group_random / rotate
        # don't hand the same products to different groups.
        used_products: set = set()
        last_group_picks: list = []

        acc_idx = 0
        for group_idx, group_id in enumerate(group_ids):
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break

            account = accounts[acc_idx % len(accounts)]
            acc_idx += 1

            if not await can_send(str(account.id)):
                await asyncio.sleep(60)
                continue

            # V15 Item 24 — re-fetch the product pool per group so prices stay current
            # mid-campaign (Redis-cached ≤5 min; the used-set dedup keys off names).
            product_pool = await get_products(pool_size) if campaign.include_products else []
            # Per-group product subset (Phase 3/4) + opening line (Phase 2).
            group_products = (
                select_group_products(product_pool, variation, per_group, weights, group_idx,
                                      used=used_products, last_picks=last_group_picks)
                if campaign.include_products else None
            )
            if group_products:
                last_group_picks = group_products
            opening_line = campaign.opening_line
            if opening_mode == "random" and campaign.opening_variants:
                opening_line = random.choice(campaign.opening_variants)

            try:
                if campaign.use_gpt and settings.openai_api_key:
                    message = await generate_message(
                        first_name="",
                        last_name="",
                        gpt_prompt=campaign.gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
                        products=group_products,
                        emoji_level=campaign.emoji_level or "medium",
                        show_prices=campaign.show_product_prices,
                        opening_mode=opening_mode,
                        opening_line=opening_line,
                        include_opt_out=campaign.include_opt_out,
                        opt_out_text=campaign.opt_out_text,
                        use_rich_formatting=getattr(campaign, "use_rich_formatting", False),
                        # V15 Items 7/17/18 — group message: no group/individual name in the greeting.
                        is_group=True,
                        product_detail_level=getattr(campaign, "product_detail_level", "medium"),
                    )
                else:
                    # Template path — still honor opening + opt-out toggles.
                    message = campaign.message_template or "پیام افراکالا"
                    message = _apply_opening(message, opening_mode, opening_line)
                    message = _apply_opt_out(message, campaign.include_opt_out, campaign.opt_out_text)

                # V16 PART 3 — append advertising links (additive; '' when the toggle is off).
                from app.services.adlinks import links_for_campaign
                message += await links_for_campaign(campaign, db)

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
