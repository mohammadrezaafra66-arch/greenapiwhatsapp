import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account_hour_schedule import AccountHourSchedule
from app.models.account_send_config import AccountSendConfig

router = APIRouter(prefix="/account-schedules", tags=["account-schedules"])


class ScheduleCreate(BaseModel):
    account_id: str
    hour_start: int
    hour_end: int
    max_per_hour: int = 0
    gpt_prompt: str | None = None
    message_template: str | None = None
    is_active: bool = True


class DelayUpdate(BaseModel):
    min_delay_seconds: int = 45
    max_delay_seconds: int = 110


@router.get("/{account_id}")
async def get_account_schedule(account_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AccountHourSchedule)
        .where(AccountHourSchedule.account_id == uuid.UUID(account_id))
        .order_by(AccountHourSchedule.hour_start)
    )
    rows = result.scalars().all()
    delay_result = await db.execute(
        select(AccountSendConfig).where(AccountSendConfig.account_id == uuid.UUID(account_id))
    )
    delay = delay_result.scalar_one_or_none()
    return {
        "account_id": account_id,
        "delay": {
            "min_delay_seconds": delay.min_delay_seconds if delay else 45,
            "max_delay_seconds": delay.max_delay_seconds if delay else 110,
        },
        "schedule": [
            {
                "id": str(r.id),
                "hour_start": r.hour_start,
                "hour_end": r.hour_end,
                "max_per_hour": r.max_per_hour,
                "gpt_prompt": r.gpt_prompt,
                "message_template": r.message_template,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@router.post("/")
async def create_schedule_slot(body: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    slot = AccountHourSchedule(
        account_id=uuid.UUID(body.account_id),
        hour_start=body.hour_start,
        hour_end=body.hour_end,
        max_per_hour=body.max_per_hour,
        gpt_prompt=body.gpt_prompt,
        message_template=body.message_template,
        is_active=body.is_active,
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return {"id": str(slot.id)}


@router.put("/{slot_id}")
async def update_schedule_slot(slot_id: str, body: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    slot = await db.get(AccountHourSchedule, uuid.UUID(slot_id))
    if not slot:
        raise HTTPException(404, "Slot not found")
    slot.hour_start = body.hour_start
    slot.hour_end = body.hour_end
    slot.max_per_hour = body.max_per_hour
    slot.gpt_prompt = body.gpt_prompt
    slot.message_template = body.message_template
    slot.is_active = body.is_active
    await db.commit()
    return {"updated": True}


@router.delete("/{slot_id}")
async def delete_schedule_slot(slot_id: str, db: AsyncSession = Depends(get_db)):
    slot = await db.get(AccountHourSchedule, uuid.UUID(slot_id))
    if not slot:
        raise HTTPException(404, "Slot not found")
    await db.delete(slot)
    await db.commit()
    return {"deleted": True}


@router.put("/{account_id}/delay")
async def update_account_delay(account_id: str, body: DelayUpdate, db: AsyncSession = Depends(get_db)):
    from app.services.delay_service import set_delay
    await set_delay(account_id, body.min_delay_seconds, body.max_delay_seconds)
    return {"account_id": account_id, "min_delay_seconds": body.min_delay_seconds, "max_delay_seconds": body.max_delay_seconds}
