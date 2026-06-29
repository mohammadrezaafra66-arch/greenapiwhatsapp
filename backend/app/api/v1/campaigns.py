from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus
from app.models.contact import Contact
from app.workers.tasks import task_run_campaign
import uuid

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    campaigns = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "status": c.status,
            "total_contacts": c.total_contacts,
            "sent_count": c.sent_count,
            "failed_count": c.failed_count,
            "created_at": str(c.created_at),
        }
        for c in campaigns
    ]


@router.post("/")
async def create_campaign(
    name: str,
    use_gpt: bool = True,
    gpt_prompt: str = None,
    message_template: str = None,
    include_products: bool = False,
    product_count: int = 3,
    send_image: bool = False,
    image_url: str = None,
    db: AsyncSession = Depends(get_db)
):
    campaign = Campaign(
        name=name,
        use_gpt=use_gpt,
        gpt_prompt=gpt_prompt,
        message_template=message_template,
        include_products=include_products,
        product_count=product_count,
        send_image=send_image,
        image_url=image_url
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {"id": str(campaign.id), "name": campaign.name}


@router.post("/{campaign_id}/contacts")
async def add_contacts_to_campaign(
    campaign_id: str,
    contact_ids: list[str],
    db: AsyncSession = Depends(get_db)
):
    """Add contacts to a campaign."""
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
    await db.commit()

    # Launch Celery task
    task_run_campaign.delay(campaign_id)
    return {"status": "started", "campaign_id": campaign_id}


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
    await db.commit()
    task_run_campaign.delay(campaign_id)
    return {"status": "resumed"}


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
        "total": campaign.total_contacts,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
        "pending": status_counts.get(MessageStatus.pending, 0),
        "progress_pct": round(
            (campaign.sent_count / campaign.total_contacts * 100)
            if campaign.total_contacts > 0 else 0, 1
        )
    }
