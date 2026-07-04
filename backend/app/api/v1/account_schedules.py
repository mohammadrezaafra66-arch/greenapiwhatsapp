import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account_hour_schedule import AccountHourSchedule
from app.models.account_send_config import AccountSendConfig

router = APIRouter(prefix="/account-schedules", tags=["account-schedules"])


HOUR_PRESETS = {
    "morning_energy": {
        "label": "صبح‌بخیر و انرژی مثبت",
        "gpt_prompt": "یک پیام صبح‌بخیر انرژی‌بخش و انگیزشی کوتاه فارسی برای مشتری بنویس. شروع پیام باید با سلام و صبح‌بخیر باشد. یک جمله انگیزشی مرتبط با موفقیت در کسب‌وکار اضافه کن.",
        "example": "صبح‌بخیر {نام} جان! امیدوارم روزتون پر از انرژی و موفقیت باشه 🌅",
    },
    "company_intro": {
        "label": "معرفی شرکت افراکالا",
        "gpt_prompt": "یک پیام کوتاه معرفی شرکت افراکالا (عمده‌فروشی لوازم خانگی) برای مشتری بنویس. نقاط قوت: قیمت مناسب، تنوع محصول، تحویل سریع.",
        "example": "سلام {نام} عزیز، افراکالا با بیش از ۲۰۰ برند لوازم خانگی در خدمت شماست 🏠",
    },
    "product_showcase": {
        "label": "معرفی محصولات با قیمت",
        "gpt_prompt": "یک پیام معرفی محصولات لوازم خانگی با قیمت روز برای مشتری بنویس. محصولات را با قیمت ذکر کن. لحن فروشندگی داشته باشد.",
        "example": "پیشنهاد ویژه امروز افراکالا: {محصول۱} {قیمت۱} | {محصول۲} {قیمت۲} 🛒",
    },
    "follow_up": {
        "label": "پیگیری و سوال از مشتری",
        "gpt_prompt": "یک پیام پیگیری دوستانه برای مشتری بنویس. بپرس آیا به محصول خاصی نیاز دارند یا سوالی دارند. لحن صمیمی.",
        "example": "سلام {نام}، امیدوارم حالتون خوب باشه. آیا در این روزها به لوازم خانگی نیاز دارید؟ 😊",
    },
    "discount_offer": {
        "label": "پیشنهاد تخفیف ویژه",
        "gpt_prompt": "یک پیام اعلام تخفیف و پیشنهاد ویژه فروش لوازم خانگی بنویس. احساس فوریت ایجاد کن. محصولات درج شده را با قیمت ذکر کن.",
        "example": "فرصت محدود! تخفیف ویژه تا آخر هفته روی {محصول} 🔥",
    },
    "evening_wrap": {
        "label": "جمع‌بندی پایان روز",
        "gpt_prompt": "یک پیام کوتاه پایان روز برای مشتری بنویس. یادآوری پیشنهاد روز، آرزوی شب‌بخیر، اعلام ساعات کاری فردا.",
        "example": "شب‌بخیر {نام} جان! فردا از ساعت ۸ در خدمتیم 🌙",
    },
}


class ScheduleCreate(BaseModel):
    account_id: str
    hour_start: int
    hour_end: int
    max_per_hour: int = 0
    gpt_prompt: str | None = None
    message_template: str | None = None
    is_active: bool = True
    include_products: bool = False  # attach products to this hour's messages


class DelayUpdate(BaseModel):
    min_delay_seconds: int = 45
    max_delay_seconds: int = 110


@router.get("/presets")
async def get_hour_presets():
    """Return available hour message presets."""
    return [
        {"key": k, "label": v["label"], "example": v["example"], "gpt_prompt": v["gpt_prompt"]}
        for k, v in HOUR_PRESETS.items()
    ]


@router.post("/{slot_id}/apply-preset")
async def apply_preset_to_slot(slot_id: str, preset_key: str, db: AsyncSession = Depends(get_db)):
    """Apply a preset GPT prompt to an existing schedule slot."""
    if preset_key not in HOUR_PRESETS:
        raise HTTPException(400, f"Unknown preset: {preset_key}")
    slot = await db.get(AccountHourSchedule, uuid.UUID(slot_id))
    if not slot:
        raise HTTPException(404, "Slot not found")
    slot.gpt_prompt = HOUR_PRESETS[preset_key]["gpt_prompt"]
    await db.commit()
    return {"applied": True, "preset": preset_key, "label": HOUR_PRESETS[preset_key]["label"]}


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
                "include_products": r.include_products,
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
        include_products=body.include_products,
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
    slot.include_products = body.include_products
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
