"""V14 FEATURE 10 — campaign recall (the "wrong price to 500 groups" panic button).

Deletes every message a campaign sent, rate-limited at 10/sec, marking each
campaign_contact recalled=true. Messages past WhatsApp's delete window simply won't
be removed (HTTP 200 with no effect) — that's expected, not an error.
"""
import asyncio
import logging
import uuid
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.campaign import Campaign, CampaignContact
from app.models.contact import Contact
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient

logger = logging.getLogger("afrakala.recall")

RATE_SLEEP = 0.1   # 10/sec cap for deleteMessage


async def recall_campaign(campaign_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign:
            return {"error": "not found"}

        rows = (await db.execute(
            select(CampaignContact, Contact)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.green_api_message_id.isnot(None),
                CampaignContact.recalled.is_(False),
            )
        )).all()

        # Cache one client per sending account.
        clients: dict = {}
        default_acc = (await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )).scalars().first()

        async def client_for(account_id):
            if account_id and account_id in clients:
                return clients[account_id]
            acc = await db.get(Account, account_id) if account_id else default_acc
            acc = acc or default_acc
            if not acc:
                return None
            c = GreenAPIClient(acc.instance_id, acc.api_token)
            clients[account_id] = c
            return c

        recalled = 0
        for cc, contact in rows:
            client = await client_for(cc.account_id)
            if not client or not contact.phone:
                continue
            try:
                await client.delete_message_raw(contact.phone, cc.green_api_message_id, only_sender=False)
                cc.recalled = True
                recalled += 1
            except Exception as e:
                logger.warning("recall delete failed (cc=%s): %s", cc.id, e)
            if recalled % 20 == 0:
                await db.commit()   # periodic checkpoint for live progress
            await asyncio.sleep(RATE_SLEEP)

        await db.commit()
        logger.info("Campaign %s recall: %d messages deleted", campaign_id, recalled)
        return {"recalled": recalled, "total": len(rows)}
