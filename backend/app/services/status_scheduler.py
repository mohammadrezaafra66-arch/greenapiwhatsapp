"""Builds and posts scheduled statuses per account per plan (V11.4)."""
import random
import logging
from datetime import datetime, timedelta
import pytz
import jdatetime
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.status_schedule import StatusSchedule
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from app.services.status_content import get_intro_text
from app.services.price_service import get_products

logger = logging.getLogger("afrakala.status_scheduler")
TEHRAN_TZ = pytz.timezone("Asia/Tehran")


def persian_dow(dt: datetime) -> int:
    """Persian week index: Saturday=0 .. Friday=6 (Python weekday Mon=0..Sun=6)."""
    return (dt.weekday() + 2) % 7


def shamsi_date_str(dt: datetime) -> str:
    return jdatetime.date.fromgregorian(date=dt.date()).strftime("%Y/%m/%d")


async def build_status_text(schedule) -> str:
    """Build the status text from the schedule config."""
    if schedule.status_type == "intro":
        return get_intro_text(schedule.intro_subtype or "history")
    if schedule.status_type == "custom":
        return schedule.custom_text or ""
    if schedule.status_type == "special_offer":
        pick = schedule.product_pick_count or 3
        pool = schedule.product_pool or []
        all_products = await get_products(200)
        if schedule.product_selection == "manual" and pool:
            # product_pool stores product NAMES (get_products exposes no id)
            candidates = [p for p in all_products if p.get("name") in pool] or all_products
        else:
            candidates = all_products
        if not candidates:
            return "🔥 پیشنهاد ویژه افراکالا 🔥\n\n📞 برای سفارش تماس بگیرید"
        products = random.sample(candidates, min(pick, len(candidates)))
        text = "🔥 پیشنهاد ویژه افراکالا 🔥\n\n"
        for p in products:
            if schedule.show_price and p.get("price"):
                text += f"• {p['name']}: {p['price']:,} تومان\n"
            else:
                text += f"• {p['name']}\n"
        text += "\n📞 برای سفارش تماس بگیرید"
        return text
    return ""


def compute_next_run(schedule, now_tehran: datetime | None = None) -> datetime | None:
    """Best-effort next run (naive UTC) by scanning the next 14 days."""
    now_tehran = now_tehran or datetime.now(TEHRAN_TZ)
    times = schedule.times or []
    if not times:
        return None
    best = None
    for offset in range(0, 15):
        day = now_tehran + timedelta(days=offset)
        dow = persian_dow(day)
        matches_day = (schedule.days_of_week and dow in schedule.days_of_week) or \
                      (schedule.specific_dates and shamsi_date_str(day) in schedule.specific_dates)
        if not matches_day:
            continue
        for t in times:
            try:
                h, m = [int(x) for x in str(t).split(":")[:2]]
            except Exception:
                continue
            cand = TEHRAN_TZ.localize(datetime(day.year, day.month, day.day, h, m))
            if cand > now_tehran and (best is None or cand < best):
                best = cand
    if best is None:
        return None
    return best.astimezone(pytz.utc).replace(tzinfo=None)


async def post_scheduled_status(schedule_id):
    """Post one scheduled status now."""
    async with AsyncSessionLocal() as db:
        schedule = await db.get(StatusSchedule, schedule_id)
        if not schedule or not schedule.is_active:
            return
        account = await db.get(Account, schedule.account_id)
        if not account or account.status != AccountStatus.active:
            return
        client = GreenAPIClient(account.instance_id, account.api_token)
        text = await build_status_text(schedule)
        try:
            if schedule.content_type in ("image", "image_caption") and schedule.image_url:
                caption = text if schedule.include_caption else ""
                await client.send_status_image(schedule.image_url, caption)
            else:
                await client.send_status_text(text)
            schedule.last_run_at = datetime.utcnow()
            schedule.next_run_at = compute_next_run(schedule)
            await db.commit()
        except Exception as e:
            logger.warning("post_scheduled_status %s failed: %s", schedule_id, e)


async def check_and_post_due_statuses():
    """Beat entry — post any schedule whose day+time matches now (Tehran), once per slot."""
    now = datetime.now(TEHRAN_TZ)
    dow = persian_dow(now)
    today_shamsi = shamsi_date_str(now)
    async with AsyncSessionLocal() as db:
        schedules = (await db.execute(
            select(StatusSchedule).where(StatusSchedule.is_active == True)
        )).scalars().all()

    for schedule in schedules:
        day_ok = (schedule.days_of_week and dow in schedule.days_of_week) or \
                 (schedule.specific_dates and today_shamsi in schedule.specific_dates)
        if not day_ok:
            continue
        due = False
        for t in (schedule.times or []):
            try:
                h, m = [int(x) for x in str(t).split(":")[:2]]
            except Exception:
                continue
            # beat runs every 5 min → fire within a 10-min window of the scheduled minute
            if now.hour == h and 0 <= (now.minute - m) < 10:
                due = True
                break
        if not due:
            continue
        # Dedup: skip if it already ran in this same Tehran date+hour slot.
        if schedule.last_run_at:
            last_teh = pytz.utc.localize(schedule.last_run_at).astimezone(TEHRAN_TZ)
            if last_teh.date() == now.date() and last_teh.hour == now.hour:
                continue
        await post_scheduled_status(schedule.id)
