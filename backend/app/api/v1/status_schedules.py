import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.status_schedule import StatusSchedule
from app.services.status_scheduler import compute_next_run
from app.utils.shamsi import to_shamsi

router = APIRouter(prefix="/status-schedules", tags=["status-schedules"])


class ScheduleBody(BaseModel):
    account_id: str
    name: str | None = None
    status_type: str = "intro"          # intro | special_offer | custom
    content_type: str = "text"          # text | text_price | image | image_caption
    intro_subtype: str | None = None
    custom_text: str | None = None
    show_price: bool = False
    include_image: bool = False
    include_caption: bool = True
    image_url: str | None = None
    product_selection: str = "random"   # manual | random
    product_pool: list | None = None    # product names
    product_pick_count: int = 3
    days_of_week: list | None = None     # [0..6] Saturday..Friday
    specific_dates: list | None = None   # ["1403/05/20", ...] Shamsi
    times: list | None = None            # ["09:00","20:00"]
    is_active: bool = True


def _serialize(s: StatusSchedule) -> dict:
    return {
        "id": str(s.id),
        "account_id": str(s.account_id) if s.account_id else None,
        "name": s.name,
        "status_type": s.status_type,
        "content_type": s.content_type,
        "intro_subtype": s.intro_subtype,
        "custom_text": s.custom_text,
        "show_price": s.show_price,
        "include_image": s.include_image,
        "include_caption": s.include_caption,
        "image_url": s.image_url,
        "product_selection": s.product_selection,
        "product_pool": s.product_pool,
        "product_pick_count": s.product_pick_count,
        "days_of_week": s.days_of_week,
        "specific_dates": s.specific_dates,
        "times": s.times,
        "is_active": s.is_active,
        "next_run_shamsi": to_shamsi(s.next_run_at),
        "last_run_shamsi": to_shamsi(s.last_run_at),
    }


def _apply(s: StatusSchedule, body: ScheduleBody):
    s.name = body.name
    s.status_type = body.status_type
    s.content_type = body.content_type
    s.intro_subtype = body.intro_subtype
    s.custom_text = body.custom_text
    s.show_price = body.show_price
    s.include_image = body.include_image
    s.include_caption = body.include_caption
    s.image_url = body.image_url
    s.product_selection = body.product_selection
    s.product_pool = body.product_pool
    s.product_pick_count = body.product_pick_count
    s.days_of_week = body.days_of_week
    s.specific_dates = body.specific_dates
    s.times = body.times
    s.is_active = body.is_active
    s.next_run_at = compute_next_run(s)


@router.get("/")
async def list_schedules(account_id: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(StatusSchedule).order_by(StatusSchedule.created_at.desc())
    if account_id:
        q = q.where(StatusSchedule.account_id == uuid.UUID(account_id))
    return [_serialize(s) for s in (await db.execute(q)).scalars().all()]


@router.post("/")
async def create_schedule(body: ScheduleBody, db: AsyncSession = Depends(get_db)):
    s = StatusSchedule(account_id=uuid.UUID(body.account_id))
    _apply(s, body)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _serialize(s)


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleBody, db: AsyncSession = Depends(get_db)):
    s = await db.get(StatusSchedule, uuid.UUID(schedule_id))
    if not s:
        raise HTTPException(404, "Schedule not found")
    s.account_id = uuid.UUID(body.account_id)
    _apply(s, body)
    await db.commit()
    return _serialize(s)


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    s = await db.get(StatusSchedule, uuid.UUID(schedule_id))
    if s:
        await db.delete(s)
        await db.commit()
    return {"deleted": True}


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    s = await db.get(StatusSchedule, uuid.UUID(schedule_id))
    if not s:
        raise HTTPException(404, "Schedule not found")
    s.is_active = not s.is_active
    await db.commit()
    return {"id": schedule_id, "is_active": s.is_active}
