"""V14 FEATURE 22 — the ban-guard pipeline for adding group participants.

Adding a non-existent number to a group can get the WhatsApp line BLOCKED, so every
add goes through: checkWhatsapp → AddContact → a strict Redis rate cap (5/min, 30/hr
per instance, stricter than the API's 10/s) → 1024-size guard → addGroupParticipant.
Failed adds fall back to offering the group invite link.
"""
import json
import logging
import asyncio
import uuid
from datetime import datetime
import pytz
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.group import WhatsAppGroup
from app.models.account import Account
from app.services.green_api import GreenAPIClient

logger = logging.getLogger("afrakala.group_add")
TEHRAN_TZ = pytz.timezone("Asia/Tehran")

MAX_PER_MINUTE = 5
MAX_PER_HOUR = 30
GROUP_SIZE_LIMIT = 1024


def _cap_keys(instance_id: str, now: datetime):
    return (
        f"groupadd:{instance_id}:{now:%Y%m%d%H%M}",   # minute bucket
        f"groupadd:{instance_id}:{now:%Y%m%d%H}",     # hour bucket
    )


def cap_ok(minute_count: int, hour_count: int) -> tuple[bool, str]:
    """Pure predicate (unit-testable). Stricter than the API — this is about BANS."""
    if minute_count >= MAX_PER_MINUTE:
        return False, "سقف افزودن عضو (۵ در دقیقه) — بقیه در نوبت هستند"
    if hour_count >= MAX_PER_HOUR:
        return False, "سقف افزودن عضو (۳۰ در ساعت) — بقیه در نوبت هستند"
    return True, "ok"


async def _redis():
    from app.services import redis_rate_limiter
    return await redis_rate_limiter.get_redis()


async def group_add_allowed(instance_id: str) -> tuple[bool, str]:
    r = await _redis()
    now = datetime.now(TEHRAN_TZ)
    min_key, hour_key = _cap_keys(instance_id, now)
    minute_count = int(await r.get(min_key) or 0)
    hour_count = int(await r.get(hour_key) or 0)
    return cap_ok(minute_count, hour_count)


async def record_group_add(instance_id: str):
    r = await _redis()
    now = datetime.now(TEHRAN_TZ)
    min_key, hour_key = _cap_keys(instance_id, now)
    pipe = r.pipeline()
    pipe.incr(min_key); pipe.expire(min_key, 120)
    pipe.incr(hour_key); pipe.expire(hour_key, 7200)
    await pipe.execute()


async def _set_progress(group_db_id: str, payload: dict):
    r = await _redis()
    await r.set(f"groupadd_progress:{group_db_id}", json.dumps(payload, ensure_ascii=False), ex=3600)


async def safe_add_participants(group_db_id: str, phones: list[str]):
    """Run the ban-guard pipeline. Publishes per-number results to Redis for the UI.
    When the rate cap is hit, the remaining numbers are re-queued for the next window."""
    async with AsyncSessionLocal() as db:
        group = await db.get(WhatsAppGroup, uuid.UUID(group_db_id))
        if not group or not group.green_group_id:
            await _set_progress(group_db_id, {"error": "group not found", "finished": True})
            return
        account = await db.get(Account, group.account_id)
        if not account:
            await _set_progress(group_db_id, {"error": "no account", "finished": True})
            return
        # TG — platform-aware client (Telegram host/chatId); WhatsApp behavior unchanged.
        client = GreenAPIClient(account.instance_id, account.api_token,
                                platform=getattr(account, "platform", "whatsapp") or "whatsapp",
                                api_host=getattr(account, "api_host", None))

        # Size guard + invite link (for failed-add fallback).
        invite_link = None
        try:
            data = await client.get_group_data(group.green_group_id)
            size = data.get("size") or len(data.get("participants") or [])
            invite_link = data.get("groupInviteLink")
            if size and int(size) >= GROUP_SIZE_LIMIT:
                await _set_progress(group_db_id, {
                    "error": f"گروه به سقف {GROUP_SIZE_LIMIT} عضو رسیده است", "finished": True})
                return
        except Exception as e:
            logger.warning("getGroupData failed for %s: %s", group.green_group_id, e)

        results = []
        remaining = list(phones)
        for idx, phone in enumerate(phones):
            # 1) existence check FIRST — the single most important ban guard.
            #    Platform-aware: WhatsApp→checkWhatsapp, Telegram→checkAccount.
            try:
                exists = await client.contact_exists(phone)
            except Exception:
                exists = False
            if not exists:
                results.append({"phone": phone, "status": "no_whatsapp"})   # ⛔ واتساپ ندارد
                remaining.remove(phone)
                await _set_progress(group_db_id, {"total": len(phones), "results": results,
                                                  "finished": False, "invite_link": invite_link})
                continue

            # 2) Rate cap (5/min, 30/hr) — queue the rest for the next window.
            allowed, reason = await group_add_allowed(account.instance_id)
            if not allowed:
                for q in remaining:
                    results.append({"phone": q, "status": "queued"})        # ⏳ در نوبت
                await _set_progress(group_db_id, {"total": len(phones), "results": results,
                                                  "finished": False, "queued_reason": reason,
                                                  "invite_link": invite_link})
                # Re-queue the remaining numbers ~1 minute later.
                try:
                    from app.workers.tasks import task_safe_add_participants
                    task_safe_add_participants.apply_async(args=[group_db_id, remaining], countdown=60)
                except Exception as e:
                    logger.warning("re-queue group adds failed: %s", e)
                return

            # 3) AddContact before adding (Green API recommends it — adds fail otherwise).
            try:
                await client.add_contact(phone, first_name=phone)
            except Exception:
                pass
            # 4) Add.
            try:
                await client.add_group_participant(group.green_group_id, phone)
                await record_group_add(account.instance_id)
                results.append({"phone": phone, "status": "added"})          # ✅ افزوده شد
                group.member_count = (group.member_count or 0) + 1
            except Exception as e:
                logger.info("add %s failed: %s", phone, e)
                results.append({"phone": phone, "status": "failed"})         # ❌ ناموفق — دعوت بفرستید
            remaining.remove(phone)
            await _set_progress(group_db_id, {"total": len(phones), "results": results,
                                              "finished": False, "invite_link": invite_link})
            await asyncio.sleep(2)   # gentle spacing (≤10/s API); cap enforces 5/min

        await db.commit()
        await _set_progress(group_db_id, {"total": len(phones), "results": results,
                                          "finished": True, "invite_link": invite_link})
