import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.database import get_db
from app.models.campaign import (
    Campaign, CampaignContact, CampaignStatus, CampaignType, MessageStatus
)
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.workers.tasks import task_run_campaign

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreateBody(BaseModel):
    name: str
    campaign_type: str = "text"
    use_gpt: bool = True
    gpt_prompt: str | None = None
    message_template: str | None = None
    include_products: bool = False
    product_count: int = 3
    image_url: str | None = None
    poll_question: str | None = None
    poll_options: list[str] | None = None
    buttons: list[str] | None = None
    footer_text: str | None = None
    campaign_scope: str = "pv"      # pv | group
    group_ids: list[str] | None = None   # list of WhatsApp group chatIds (e.g. "120363xxxxxxxx@g.us")


class TestBody(BaseModel):
    phone: str
    message: str | None = None


@router.get("/")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    campaigns = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "status": c.status,
            "pause_reason": c.pause_reason,
            "campaign_type": c.campaign_type,
            "total_contacts": c.total_contacts,
            "sent_count": c.sent_count,
            "failed_count": c.failed_count,
            "delivered_count": c.delivered_count,
            "read_count": c.read_count,
            "created_at": str(c.created_at),
        }
        for c in campaigns
    ]


@router.post("/")
async def create_campaign(body: CampaignCreateBody, db: AsyncSession = Depends(get_db)):
    try:
        ctype = CampaignType(body.campaign_type)
    except ValueError:
        raise HTTPException(400, f"Invalid campaign_type: {body.campaign_type}")

    buttons = body.buttons or []
    campaign = Campaign(
        name=body.name,
        campaign_type=ctype,
        use_gpt=body.use_gpt,
        gpt_prompt=body.gpt_prompt,
        message_template=body.message_template,
        include_products=body.include_products,
        product_count=body.product_count,
        image_url=body.image_url,
        poll_question=body.poll_question,
        poll_options=json.dumps(body.poll_options, ensure_ascii=False) if body.poll_options else None,
        button1_text=buttons[0] if len(buttons) > 0 else None,
        button2_text=buttons[1] if len(buttons) > 1 else None,
        button3_text=buttons[2] if len(buttons) > 2 else None,
        footer_text=body.footer_text,
        campaign_scope=body.campaign_scope,
        group_ids=json.dumps(body.group_ids) if body.group_ids else None,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {"id": str(campaign.id), "name": campaign.name, "campaign_type": campaign.campaign_type}


@router.post("/{campaign_id}/contacts")
async def add_contacts_to_campaign(
    campaign_id: str,
    contact_ids: list[str],
    db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    count = 0
    for cid in contact_ids:
        cc = CampaignContact(
            campaign_id=campaign.id,
            contact_id=uuid.UUID(cid),
            status=MessageStatus.pending
        )
        db.add(cc)
        count += 1

    campaign.total_contacts += count
    await db.commit()
    return {"added": count}


@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign.status == CampaignStatus.running:
        raise HTTPException(400, "Campaign already running")
    campaign.status = CampaignStatus.running
    campaign.pause_reason = None
    await db.commit()
    if campaign.campaign_scope == "group":
        from app.workers.tasks import task_run_group_campaign
        task_run_group_campaign.delay(campaign_id)
    else:
        task_run_campaign.delay(campaign_id)
    return {"status": "started", "campaign_id": campaign_id, "scope": campaign.campaign_scope}


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    campaign.status = CampaignStatus.paused
    await db.commit()
    return {"status": "paused"}


@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    campaign.status = CampaignStatus.running
    campaign.pause_reason = None
    await db.commit()
    task_run_campaign.delay(campaign_id)
    return {"status": "resumed"}


@router.post("/{campaign_id}/test")
async def test_campaign(campaign_id: str, body: TestBody, db: AsyncSession = Depends(get_db)):
    """Send a single test message for this campaign to one phone number."""
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available to send test")

    from app.services.green_api import GreenAPIClient
    client = GreenAPIClient(account.instance_id, account.api_token)
    message = body.message or campaign.message_template or "پیام تستی افراکالا"

    msg_id = None
    if campaign.campaign_type == CampaignType.image and campaign.image_url:
        msg_id = await client.send_image(body.phone, campaign.image_url, message)
    elif campaign.campaign_type == CampaignType.poll and campaign.poll_question:
        opts = json.loads(campaign.poll_options) if campaign.poll_options else []
        msg_id = await client.send_poll(body.phone, campaign.poll_question, opts)
    elif campaign.campaign_type == CampaignType.interactive_buttons:
        buttons = [b for b in [campaign.button1_text, campaign.button2_text, campaign.button3_text] if b]
        msg_id = await client.send_interactive_buttons(body.phone, message, buttons, campaign.footer_text or "")
    else:
        msg_id = await client.send_message(body.phone, message)

    return {"sent": bool(msg_id), "message_id": msg_id, "via": account.name}


@router.get("/{campaign_id}/progress")
async def campaign_progress(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    stats = await db.execute(
        select(CampaignContact.status, func.count())
        .where(CampaignContact.campaign_id == campaign.id)
        .group_by(CampaignContact.status)
    )
    status_counts = {row[0]: row[1] for row in stats.all()}

    return {
        "campaign_id": campaign_id,
        "name": campaign.name,
        "status": campaign.status,
        "pause_reason": campaign.pause_reason,
        "total": campaign.total_contacts,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
        "delivered": campaign.delivered_count,
        "read": campaign.read_count,
        "pending": status_counts.get(MessageStatus.pending, 0),
        "progress_pct": round(
            (campaign.sent_count / campaign.total_contacts * 100)
            if campaign.total_contacts > 0 else 0, 1
        )
    }


@router.get("/{campaign_id}/contacts")
async def campaign_contacts(
    campaign_id: str,
    status: str = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    """List a campaign's contacts, optionally filtered by status (e.g. failed).
    Includes error_message so the frontend can show why sends failed."""
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    query = (
        select(CampaignContact, Contact)
        .join(Contact, CampaignContact.contact_id == Contact.id)
        .where(CampaignContact.campaign_id == campaign.id)
    )
    if status:
        try:
            query = query.where(CampaignContact.status == MessageStatus(status))
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    query = query.order_by(CampaignContact.sent_at.desc().nullslast()).limit(limit)

    rows = (await db.execute(query)).all()
    return [
        {
            "id": str(cc.id),
            "phone": contact.phone,
            "name": contact.full_name,
            "status": cc.status,
            "error_message": cc.error_message,
            "retry_count": cc.retry_count,
            "sent_at": str(cc.sent_at) if cc.sent_at else None,
            "green_api_message_id": cc.green_api_message_id,
            "delivery_status": cc.delivery_status,
        }
        for cc, contact in rows
    ]


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    await db.execute(delete(CampaignContact).where(CampaignContact.campaign_id == campaign.id))
    await db.delete(campaign)
    await db.commit()
    return {"success": True}
