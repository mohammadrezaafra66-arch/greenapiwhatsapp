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
from app.utils.shamsi import to_shamsi, from_shamsi

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
    # V5 extensions
    description: str | None = None
    append_date: bool = False
    append_seller_name: bool = False
    seller_name: str | None = None
    append_seller_phone: bool = False
    seller_phone: str | None = None
    seller_phone2: str | None = None
    emoji_level: str = "medium"  # none/low/medium/high
    contact_group_id: str | None = None  # use contacts from this group
    wa_collection_id: str | None = None  # send to WA groups in this collection
    product_label_filter: str | None = None  # filter products by label id
    is_always_on: bool = False
    is_active: bool = True
    # V8 extensions
    schedule_start_shamsi: str | None = None  # "1403/01/15 08:00"
    schedule_end_shamsi: str | None = None    # "1403/01/20 22:00"
    parallel_accounts: bool = False
    max_parallel_accounts: int = 1
    show_product_prices: bool = True
    # Message customization
    opening_mode: str = "ai"                       # ai | fixed | none | random
    opening_line: str | None = None                # for fixed mode
    opening_variants: list[str] | None = None      # for random mode
    product_variation_mode: str = "same"           # same | per_group_random | rotate
    products_per_group: int = 3
    product_weights: dict | None = None            # {product_name: weight}
    include_opt_out: bool = True
    opt_out_text: str | None = None
    # A/B testing (V13.1)
    ab_test_enabled: bool = False
    variant_b_prompt: str | None = None
    variant_b_template: str | None = None
    # Rich formatting (V13.5)
    use_rich_formatting: bool = False
    # Smart rotation (V13.2)
    smart_rotation: bool = False
    # Drip sending (V13.8)
    drip_enabled: bool = False
    drip_per_day: int = 50
    # V14 F7 — interactive buttons
    use_interactive_buttons: bool = False
    buttons_config: list[dict] | None = None
    button_header: str | None = None
    button_footer: str | None = None


class TestBody(BaseModel):
    phone: str
    message: str | None = None


class CampaignPreviewBody(BaseModel):
    """V13.6 — everything that affects the built message, so preview == real output."""
    use_gpt: bool = True
    gpt_prompt: str | None = None
    message_template: str | None = None
    include_products: bool = False
    product_count: int = 3
    product_label_filter: str | None = None
    show_product_prices: bool = True
    emoji_level: str = "medium"
    opening_mode: str = "ai"
    opening_line: str | None = None
    opening_variants: list[str] | None = None
    include_opt_out: bool = True
    opt_out_text: str | None = None
    use_rich_formatting: bool = False
    append_seller_name: bool = False
    seller_name: str | None = None
    append_seller_phone: bool = False
    seller_phone: str | None = None
    seller_phone2: str | None = None
    append_date: bool = False
    sample_first_name: str | None = None
    sample_last_name: str | None = None


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
            "description": c.description,
            "is_active": c.is_active,
            "total_contacts": c.total_contacts,
            "sent_count": c.sent_count,
            "failed_count": c.failed_count,
            "delivered_count": c.delivered_count,
            "read_count": c.read_count,
            "parallel_accounts": c.parallel_accounts,
            "schedule_start_shamsi": to_shamsi(c.schedule_start),
            "schedule_end_shamsi": to_shamsi(c.schedule_end),
            "created_at": str(c.created_at),
        }
        for c in campaigns
    ]


def _campaign_detail(c: Campaign) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "status": c.status,
        "campaign_type": c.campaign_type,
        "use_gpt": c.use_gpt,
        "gpt_prompt": c.gpt_prompt,
        "message_template": c.message_template,
        "include_products": c.include_products,
        "product_count": c.product_count,
        "image_url": c.image_url,
        "campaign_scope": c.campaign_scope,
        "group_ids": json.loads(c.group_ids) if c.group_ids else None,
        "description": c.description,
        "is_active": c.is_active,
        "append_date": c.append_date,
        "append_seller_name": c.append_seller_name,
        "seller_name": c.seller_name,
        "append_seller_phone": c.append_seller_phone,
        "seller_phone": c.seller_phone,
        "seller_phone2": c.seller_phone2,
        "emoji_level": c.emoji_level,
        "contact_group_id": str(c.contact_group_id) if c.contact_group_id else None,
        "wa_collection_id": str(c.wa_collection_id) if c.wa_collection_id else None,
        "product_label_filter": c.product_label_filter,
        "is_always_on": c.is_always_on,
        "parallel_accounts": c.parallel_accounts,
        "max_parallel_accounts": c.max_parallel_accounts,
        "show_product_prices": c.show_product_prices,
        "schedule_start_shamsi": to_shamsi(c.schedule_start),
        "schedule_end_shamsi": to_shamsi(c.schedule_end),
        "ab_test_enabled": c.ab_test_enabled,
        "variant_b_prompt": c.variant_b_prompt,
        "variant_b_template": c.variant_b_template,
        "use_rich_formatting": c.use_rich_formatting,
        "smart_rotation": c.smart_rotation,
        "drip_enabled": c.drip_enabled,
        "drip_per_day": c.drip_per_day,
    }


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, uuid.UUID(campaign_id))
    if not c:
        raise HTTPException(404, "Campaign not found")
    return _campaign_detail(c)


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: str, body: CampaignCreateBody, db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, uuid.UUID(campaign_id))
    if not c:
        raise HTTPException(404, "Campaign not found")
    try:
        c.campaign_type = CampaignType(body.campaign_type)
    except ValueError:
        raise HTTPException(400, f"Invalid campaign_type: {body.campaign_type}")
    buttons = body.buttons or []
    c.name = body.name
    c.use_gpt = body.use_gpt
    c.gpt_prompt = body.gpt_prompt
    c.message_template = body.message_template
    c.include_products = body.include_products
    c.product_count = body.product_count
    c.image_url = body.image_url
    c.poll_question = body.poll_question
    c.poll_options = json.dumps(body.poll_options, ensure_ascii=False) if body.poll_options else None
    c.button1_text = buttons[0] if len(buttons) > 0 else None
    c.button2_text = buttons[1] if len(buttons) > 1 else None
    c.button3_text = buttons[2] if len(buttons) > 2 else None
    c.footer_text = body.footer_text
    c.campaign_scope = body.campaign_scope
    c.group_ids = json.dumps(body.group_ids) if body.group_ids else None
    c.description = body.description
    c.append_date = body.append_date
    c.append_seller_name = body.append_seller_name
    c.seller_name = body.seller_name
    c.append_seller_phone = body.append_seller_phone
    c.seller_phone = body.seller_phone
    c.seller_phone2 = body.seller_phone2
    c.emoji_level = body.emoji_level or "medium"
    c.contact_group_id = uuid.UUID(body.contact_group_id) if body.contact_group_id else None
    c.wa_collection_id = uuid.UUID(body.wa_collection_id) if body.wa_collection_id else None
    c.product_label_filter = body.product_label_filter
    c.is_always_on = body.is_always_on
    c.is_active = body.is_active
    c.parallel_accounts = body.parallel_accounts
    c.max_parallel_accounts = body.max_parallel_accounts
    c.show_product_prices = body.show_product_prices
    if body.schedule_start_shamsi is not None:
        c.schedule_start = from_shamsi(body.schedule_start_shamsi)
    if body.schedule_end_shamsi is not None:
        c.schedule_end = from_shamsi(body.schedule_end_shamsi)
    c.ab_test_enabled = body.ab_test_enabled
    c.variant_b_prompt = body.variant_b_prompt
    c.variant_b_template = body.variant_b_template
    c.use_rich_formatting = body.use_rich_formatting
    c.smart_rotation = body.smart_rotation
    c.drip_enabled = body.drip_enabled
    c.drip_per_day = body.drip_per_day or 50
    # V14 F7 — interactive buttons
    if body.use_interactive_buttons and body.buttons_config:
        from app.services.interactive import validate_buttons
        try:
            validate_buttons(body.buttons_config)
        except ValueError as e:
            raise HTTPException(400, str(e))
    c.use_interactive_buttons = body.use_interactive_buttons
    c.buttons_config = body.buttons_config or None
    c.button_header = body.button_header
    c.button_footer = body.button_footer
    await db.commit()
    return {"id": campaign_id, "updated": True}


@router.post("/{campaign_id}/recall")
async def recall_campaign_endpoint(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """V14 F10 — delete every message this campaign sent (background, 10/sec).
    Group campaigns are not supported (the per-contact chat differs from the group)."""
    c = await db.get(Campaign, uuid.UUID(campaign_id))
    if not c:
        raise HTTPException(404, "Campaign not found")
    if (c.campaign_scope or "pv") == "group":
        raise HTTPException(400, "فراخوانی برای کمپین‌های گروهی پشتیبانی نمی‌شود")
    total = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.campaign_id == c.id,
            CampaignContact.green_api_message_id.isnot(None),
        )
    )).scalar() or 0
    if total == 0:
        raise HTTPException(400, "پیامی برای حذف یافت نشد")
    from app.workers.tasks import task_recall_campaign
    task_recall_campaign.delay(campaign_id)
    return {"started": True, "total": total}


@router.get("/{campaign_id}/recall-progress")
async def recall_progress(campaign_id: str, db: AsyncSession = Depends(get_db)):
    cid = uuid.UUID(campaign_id)
    total = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.campaign_id == cid,
            CampaignContact.green_api_message_id.isnot(None),
        )
    )).scalar() or 0
    recalled = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.campaign_id == cid,
            CampaignContact.recalled.is_(True),
        )
    )).scalar() or 0
    return {"total": total, "recalled": recalled, "done": recalled >= total}


@router.post("/{campaign_id}/toggle-active")
async def toggle_campaign_active(campaign_id: str, db: AsyncSession = Depends(get_db)):
    c = await db.get(Campaign, uuid.UUID(campaign_id))
    if not c:
        raise HTTPException(404, "Campaign not found")
    c.is_active = not c.is_active
    await db.commit()
    return {"id": campaign_id, "is_active": c.is_active}


@router.post("/")
async def create_campaign(body: CampaignCreateBody, db: AsyncSession = Depends(get_db)):
    try:
        ctype = CampaignType(body.campaign_type)
    except ValueError:
        raise HTTPException(400, f"Invalid campaign_type: {body.campaign_type}")

    buttons = body.buttons or []
    if body.use_interactive_buttons and body.buttons_config:
        from app.services.interactive import validate_buttons
        try:
            validate_buttons(body.buttons_config)
        except ValueError as e:
            raise HTTPException(400, str(e))
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
        description=body.description,
        append_date=body.append_date,
        append_seller_name=body.append_seller_name,
        seller_name=body.seller_name,
        append_seller_phone=body.append_seller_phone,
        seller_phone=body.seller_phone,
        seller_phone2=body.seller_phone2,
        emoji_level=body.emoji_level or "medium",
        contact_group_id=uuid.UUID(body.contact_group_id) if body.contact_group_id else None,
        wa_collection_id=uuid.UUID(body.wa_collection_id) if body.wa_collection_id else None,
        product_label_filter=body.product_label_filter,
        is_always_on=body.is_always_on,
        is_active=body.is_active,
        parallel_accounts=body.parallel_accounts,
        max_parallel_accounts=body.max_parallel_accounts,
        show_product_prices=body.show_product_prices,
        schedule_start=from_shamsi(body.schedule_start_shamsi) if body.schedule_start_shamsi else None,
        schedule_end=from_shamsi(body.schedule_end_shamsi) if body.schedule_end_shamsi else None,
        opening_mode=body.opening_mode or "ai",
        opening_line=body.opening_line,
        opening_variants=body.opening_variants or None,
        product_variation_mode=body.product_variation_mode or "same",
        products_per_group=body.products_per_group or 3,
        product_weights=body.product_weights or None,
        include_opt_out=body.include_opt_out,
        opt_out_text=body.opt_out_text,
        ab_test_enabled=body.ab_test_enabled,
        variant_b_prompt=body.variant_b_prompt,
        variant_b_template=body.variant_b_template,
        use_rich_formatting=body.use_rich_formatting,
        smart_rotation=body.smart_rotation,
        drip_enabled=body.drip_enabled,
        drip_per_day=body.drip_per_day or 50,
        use_interactive_buttons=body.use_interactive_buttons,
        buttons_config=body.buttons_config or None,
        button_header=body.button_header,
        button_footer=body.button_footer,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {"id": str(campaign.id), "name": campaign.name, "campaign_type": campaign.campaign_type}


@router.post("/preview")
async def preview_message(body: CampaignPreviewBody, db: AsyncSession = Depends(get_db)):
    """V13.6 — return the FULLY BUILT message text exactly as the runner would produce
    it (same build_message_text path), without sending. Uses a sample contact."""
    from types import SimpleNamespace
    from app.models.contact import Contact
    from app.services.campaign_runner import build_message_text
    from app.services.price_service import get_products, get_products_by_label

    products = []
    if body.include_products:
        if body.product_label_filter:
            products = await get_products_by_label(body.product_label_filter, body.product_count)
        else:
            products = await get_products(body.product_count)

    campaign = SimpleNamespace(
        use_gpt=body.use_gpt, gpt_prompt=body.gpt_prompt, message_template=body.message_template,
        include_products=body.include_products, product_count=body.product_count,
        show_product_prices=body.show_product_prices, emoji_level=body.emoji_level,
        opening_mode=body.opening_mode, opening_line=body.opening_line, opening_variants=body.opening_variants,
        include_opt_out=body.include_opt_out, opt_out_text=body.opt_out_text,
        use_rich_formatting=body.use_rich_formatting,
        append_seller_name=body.append_seller_name, seller_name=body.seller_name,
        append_seller_phone=body.append_seller_phone, seller_phone=body.seller_phone,
        seller_phone2=body.seller_phone2, append_date=body.append_date,
    )

    # Sample contact: explicit override → first real contact → dummy.
    if body.sample_first_name or body.sample_last_name:
        contact = SimpleNamespace(first_name=body.sample_first_name or "",
                                  last_name=body.sample_last_name or "", city="", province="")
    else:
        row = (await db.execute(select(Contact).limit(1))).scalars().first()
        if row:
            contact = SimpleNamespace(first_name=row.first_name or "", last_name=row.last_name or "",
                                      city=row.city or "", province=row.province or "")
        else:
            contact = SimpleNamespace(first_name="دوست", last_name="", city="", province="")

    text = await build_message_text(campaign, contact, products, campaign.gpt_prompt,
                                    campaign.message_template, campaign.include_products)
    return {"preview": text}


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

    # If a contact group is set, auto-add its contacts as campaign_contacts.
    if campaign.contact_group_id:
        from app.models.contact_group import ContactGroupMember
        member_rows = await db.execute(
            select(ContactGroupMember.contact_id).where(
                ContactGroupMember.group_id == campaign.contact_group_id
            )
        )
        existing_rows = await db.execute(
            select(CampaignContact.contact_id).where(CampaignContact.campaign_id == campaign.id)
        )
        existing_ids = {r for r in existing_rows.scalars().all()}
        added = 0
        for cid in member_rows.scalars().all():
            if cid in existing_ids:
                continue
            db.add(CampaignContact(campaign_id=campaign.id, contact_id=cid, status=MessageStatus.pending))
            added += 1
        campaign.total_contacts += added

    # If a WA collection is set, target its groups.
    if campaign.wa_collection_id:
        from app.models.contact_group import WaGroupCollectionMember
        grp_rows = await db.execute(
            select(WaGroupCollectionMember.group_chat_id).where(
                WaGroupCollectionMember.collection_id == campaign.wa_collection_id
            )
        )
        chat_ids = [g for g in grp_rows.scalars().all()]
        if chat_ids:
            campaign.campaign_scope = "group"
            campaign.group_ids = json.dumps(chat_ids)

    # V13.1 — A/B test: assign each still-pending contact a variant, alternating
    # A/B (deterministic ~50/50). Only contacts without a variant yet are touched.
    if campaign.ab_test_enabled and campaign.campaign_scope != "group":
        cc_rows = (await db.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == MessageStatus.pending,
                CampaignContact.ab_variant.is_(None),
            ).order_by(CampaignContact.id)
        )).scalars().all()
        for i, cc in enumerate(cc_rows):
            cc.ab_variant = "A" if i % 2 == 0 else "B"

    campaign.status = CampaignStatus.running
    campaign.pause_reason = None
    await db.commit()
    if campaign.campaign_scope == "group":
        from app.workers.tasks import task_run_group_campaign
        task_run_group_campaign.delay(campaign_id)
    elif campaign.parallel_accounts:
        # Feature 37 — split contacts across all active accounts, sent concurrently.
        acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
        active_accounts = [str(a.id) for a in acc_result.scalars().all()]
        task_run_campaign.delay(campaign_id, active_accounts)
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


@router.post("/{campaign_id}/retry-failed")
async def retry_failed(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """D1 — re-queue ONLY the failed / yellowCard contacts of a campaign."""
    from sqlalchemy import update, or_
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    result = await db.execute(
        update(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign.id,
            or_(
                CampaignContact.status == MessageStatus.failed,
                CampaignContact.delivery_status == "yellowCard",
            ),
        )
        .values(status=MessageStatus.pending, error_message=None, delivery_status=None)
    )
    count = result.rowcount or 0
    if count:
        campaign.status = CampaignStatus.running
        campaign.pause_reason = None
    await db.commit()
    if count:
        task_run_campaign.delay(campaign_id)  # single-run lock prevents duplicates
    return {"requeued": count}


class OutcomeBody(BaseModel):
    outcome: str | None = None  # interested | purchased | not_interested
    note: str | None = None


@router.put("/{campaign_id}/contacts/{cc_id}/outcome")
async def set_contact_outcome(campaign_id: str, cc_id: str, body: OutcomeBody, db: AsyncSession = Depends(get_db)):
    """V13.7 — tag one campaign contact's outcome (cc_id = campaign_contacts.id)."""
    cc = await db.get(CampaignContact, uuid.UUID(cc_id))
    if not cc or str(cc.campaign_id) != str(uuid.UUID(campaign_id)):
        raise HTTPException(404, "Campaign contact not found")
    if body.outcome not in (None, "interested", "purchased", "not_interested"):
        raise HTTPException(400, "invalid outcome")
    cc.outcome = body.outcome
    cc.outcome_note = body.note
    await db.commit()
    return {"status": "ok", "outcome": cc.outcome}


@router.get("/{campaign_id}/roi")
async def campaign_roi(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """V13.7 — reply/outcome funnel: sent → delivered → read → replied → purchased."""
    from sqlalchemy import func as f, case
    from app.models.contact import Contact
    cid = uuid.UUID(campaign_id)
    agg = (await db.execute(
        select(
            f.count().label("total"),
            f.sum(case((CampaignContact.status == MessageStatus.sent, 1), else_=0)).label("sent"),
            f.sum(case((CampaignContact.delivery_status.in_(["delivered", "read"]), 1), else_=0)).label("delivered"),
            f.sum(case((CampaignContact.delivery_status == "read", 1), else_=0)).label("read"),
            f.sum(case((CampaignContact.replied == True, 1), else_=0)).label("replied"),
            f.sum(case((CampaignContact.outcome == "interested", 1), else_=0)).label("interested"),
            f.sum(case((CampaignContact.outcome == "purchased", 1), else_=0)).label("purchased"),
        ).where(CampaignContact.campaign_id == cid)
    )).first()
    sent = int(agg.sent or 0)
    replied = int(agg.replied or 0)
    replied_rows = (await db.execute(
        select(CampaignContact, Contact)
        .join(Contact, CampaignContact.contact_id == Contact.id)
        .where(CampaignContact.campaign_id == cid, CampaignContact.replied == True)
        .order_by(CampaignContact.sent_at.desc()).limit(200)
    )).all()
    return {
        "funnel": {
            "sent": sent,
            "delivered": int(agg.delivered or 0),
            "read": int(agg.read or 0),
            "replied": replied,
            "purchased": int(agg.purchased or 0),
        },
        "interested": int(agg.interested or 0),
        "purchased": int(agg.purchased or 0),
        "reply_rate": round(100 * replied / sent, 1) if sent else 0.0,
        "replied_contacts": [
            {"cc_id": str(cc.id), "phone": c.phone, "name": c.full_name,
             "outcome": cc.outcome, "note": cc.outcome_note}
            for cc, c in replied_rows
        ],
    }


@router.get("/{campaign_id}/ab-results")
async def ab_results(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """V13.1 — per-variant delivery/read stats for an A/B campaign + the winner
    (higher read%, tiebreak delivered%)."""
    from sqlalchemy import func as f, case
    rows = await db.execute(
        select(
            CampaignContact.ab_variant,
            f.count().label("total"),
            f.sum(case((CampaignContact.delivery_status == "delivered", 1), else_=0)).label("delivered"),
            f.sum(case((CampaignContact.delivery_status == "read", 1), else_=0)).label("read"),
            f.sum(case((CampaignContact.status == MessageStatus.failed, 1), else_=0)).label("failed"),
        ).where(CampaignContact.campaign_id == uuid.UUID(campaign_id))
         .group_by(CampaignContact.ab_variant)
    )
    variants = {}
    for r in rows.all():
        if not r.ab_variant:
            continue
        total = r.total or 1
        variants[r.ab_variant] = {
            "total": r.total, "delivered": r.delivered or 0, "read": r.read or 0, "failed": r.failed or 0,
            "delivered_pct": round(100 * (r.delivered or 0) / total, 1),
            "read_pct": round(100 * (r.read or 0) / total, 1),
        }
    winner = None
    if "A" in variants and "B" in variants:
        a, b = variants["A"], variants["B"]
        winner = "A" if (a["read_pct"], a["delivered_pct"]) >= (b["read_pct"], b["delivered_pct"]) else "B"
    return {"variants": variants, "winner": winner}


@router.get("/{campaign_id}/analytics")
async def campaign_analytics(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """D3 — per-campaign delivery report: counts, rates, per-account breakdown."""
    from sqlalchemy import func, case
    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    st = CampaignContact.status
    ds = CampaignContact.delivery_status

    def s(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    row = (await db.execute(
        select(
            func.count().label("total"),
            s(st == MessageStatus.sent).label("sent"),
            s(st == MessageStatus.pending).label("pending"),
            s(st == MessageStatus.failed).label("failed"),
            s(st == MessageStatus.skipped).label("skipped"),
            s(ds == "delivered").label("delivered"),
            s(ds == "read").label("read"),
            s(ds == "yellowCard").label("yellow_card"),
        ).where(CampaignContact.campaign_id == campaign.id)
    )).one()

    total = row.total or 0
    sent = row.sent or 0

    def pct(n, d):
        return round(n / d * 100, 1) if d else 0.0

    # per-account breakdown (only rows that were actually sent)
    acc_rows = (await db.execute(
        select(
            CampaignContact.account_id,
            func.count().label("sent"),
            s(ds == "read").label("read"),
            s(ds == "yellowCard").label("yellow_card"),
        )
        .where(CampaignContact.campaign_id == campaign.id, CampaignContact.account_id.isnot(None))
        .group_by(CampaignContact.account_id)
    )).all()
    accs = (await db.execute(select(Account))).scalars().all()
    names = {a.id: a.name for a in accs}

    return {
        "campaign": campaign.name,
        "status": campaign.status,
        "totals": {
            "total": total,
            "sent": sent,
            "pending": row.pending or 0,
            "failed": row.failed or 0,
            "skipped": row.skipped or 0,
            "delivered": row.delivered or 0,
            "read": row.read or 0,
            "yellow_card": row.yellow_card or 0,
        },
        "rates": {
            "sent_pct": pct(sent, total),
            "read_pct": pct(row.read or 0, sent),
            "yellow_card_pct": pct(row.yellow_card or 0, sent),
            "failed_pct": pct(row.failed or 0, total),
        },
        "per_account": [
            {
                "account_id": str(r.account_id),
                "name": names.get(r.account_id, "نامشخص"),
                "sent": r.sent,
                "read": r.read,
                "yellow_card": r.yellow_card,
            }
            for r in sorted(acc_rows, key=lambda x: x.sent, reverse=True)
        ],
    }


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
    pending = status_counts.get(MessageStatus.pending, 0)

    # V13.8 — drip progress (today's per-campaign send count from Redis).
    drip = None
    if campaign.drip_enabled:
        from app.services.drip import drip_count_today
        sent_today = await drip_count_today(campaign_id)
        per_day = campaign.drip_per_day or 50
        drip = {
            "enabled": True,
            "per_day": per_day,
            "sent_today": sent_today,
            "remaining_today": max(0, per_day - sent_today),
            "est_days_remaining": (pending + per_day - 1) // per_day if per_day else None,
        }

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
        "pending": pending,
        "drip": drip,
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
