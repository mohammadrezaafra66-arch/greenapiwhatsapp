from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.services.warmup_auto import (
    warmup_day as _warmup_day, warmup_daily_limit as _warmup_daily_limit,
    WARMUP_TOTAL_DAYS as _WARMUP_TOTAL,
)
from app.config import settings
import os
import uuid
import logging

_logger = logging.getLogger("afrakala.accounts")

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AutoReplyUpdate(BaseModel):
    auto_reply_enabled: bool | None = None
    auto_reply_message: str | None = None
    auto_reply_outside_hours: bool | None = None
    warmup_enabled: bool | None = None
    polling_enabled: bool | None = None


class AccountLimitsUpdate(BaseModel):
    max_daily_absolute: int = 200
    incoming_ratio_multiplier: float = 0.5
    max_sends_per_minute: float = 2.0


@router.get("/")
async def list_accounts(db: AsyncSession = Depends(get_db)):
    # Hide soft-deleted accounts (status='deleted') from the UI.
    result = await db.execute(
        select(Account).where(Account.status != AccountStatus.deleted).order_by(Account.created_at.desc())
    )
    accounts = result.scalars().all()
    # V18 PART 2 — the warm-up toggle now reflects the V17 enrollment, not the legacy flag.
    from app.services.warmup_exclusion import enrollment_states_by_instance
    enr_map = await enrollment_states_by_instance(db)
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "instance_id": a.instance_id,
            "phone": a.phone,
            "status": a.status,
            "sent_today": a.sent_today,
            "received_today": a.received_today,
            "daily_limit": a.computed_daily_limit,
            "days_active": a.days_active,
            "warmup_enabled": a.warmup_enabled,
            "auto_reply_enabled": a.auto_reply_enabled,
            "auto_reply_outside_hours": a.auto_reply_outside_hours,
            "is_default": a.is_default,
            "proxy_enabled": a.proxy_enabled,
            "profile_picture_url": a.profile_picture_url,
            # V15 Item 26 — legacy auto warm-up status (kept for backward compat)
            "auto_warmup": a.auto_warmup,
            "warmup_completed": a.warmup_completed,
            "warmup_day": (_warmup_day(a) if a.auto_warmup and not a.warmup_completed else None),
            "warmup_total_days": _WARMUP_TOTAL,
            "warmup_daily_limit": (_warmup_daily_limit(_warmup_day(a)) if a.auto_warmup and not a.warmup_completed else None),
            # V18 PART 2 — V17 mesh enrollment (source of truth for the toggle)
            "warmup_enrolled": bool(enr_map.get(a.instance_id, (None, False))[1]),
            "warmup_state": (enr_map.get(a.instance_id) or (None, None))[0],
            # V20 PART 2 — warm PEER (sender) role: independent of being warmed
            "is_warm_peer": bool(a.is_warm_peer),
            # V26 — dedicated group-monitoring listener role (mutually exclusive)
            "is_listener": bool(getattr(a, "is_listener", False)),
        }
        for a in accounts
    ]


@router.post("/")
async def create_account(
    name: str,
    instance_id: str,
    api_token: str,
    db: AsyncSession = Depends(get_db)
):
    # V15 Item 13 — harden the root cause of stray/phantom accounts: trim input and
    # require a real instance id + token (a blank/whitespace entry created the 9048249558
    # phantom that pointed at a non-existent Green API instance).
    name = (name or "").strip()
    instance_id = (instance_id or "").strip()
    api_token = (api_token or "").strip()
    if not instance_id or not api_token:
        raise HTTPException(400, "شناسه instance و توکن اتصال هر دو لازم است")
    if not name:
        name = instance_id
    existing = (await db.execute(select(Account).where(Account.instance_id == instance_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "این شناسه instance قبلاً ثبت شده است")
    account = Account(name=name, instance_id=instance_id, api_token=api_token)
    db.add(account)
    await db.commit()
    await db.refresh(account)

    webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/{instance_id}"
    client = GreenAPIClient(instance_id, api_token)
    try:
        await client.set_webhook(webhook_url, delay_ms=15000)
    except Exception as e:
        print(f"Warning: Could not set webhook: {e}")

    return {"id": str(account.id), "name": account.name, "status": account.status}


async def _get_account(account_id: str, db: AsyncSession) -> Account:
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@router.get("/{account_id}/daily-limit-detail")
async def get_daily_limit_detail(account_id: str, db: AsyncSession = Depends(get_db)):
    """Daily limit with full breakdown and Meta compliance notes (Feature 39)."""
    account = await _get_account(account_id, db)
    days = account.days_active or 0
    absolute = account.max_daily_absolute or 200

    base = min(days, 10)
    incoming = min(int((account.received_yesterday or 0) * (account.incoming_ratio_multiplier or 0.5)), 20)
    replies = min((account.quick_replies_yesterday or 0) * 5, 50)
    calculated = base + incoming + replies

    if days < 7:
        effective = min(5, absolute)
        week1_cap = True
    else:
        effective = min(calculated, absolute)
        week1_cap = False

    return {
        "account_name": account.name,
        "days_active": days,
        "sent_today": account.sent_today,
        "remaining_today": max(0, effective - account.sent_today),
        "effective_limit": effective,
        "breakdown": {
            "base_days": base,
            "incoming_bonus": incoming,
            "reply_bonus": replies,
            "calculated": calculated,
            "absolute_cap": absolute,
            "week1_cap_active": week1_cap,
        },
        "explanation": (
            f"هفته اول (روز {days}/7) — سقف ۵ پیام" if week1_cap else
            f"پایه: {base} + دریافتی: {incoming} + پاسخ: {replies} = {calculated} (سقف: {absolute})"
        ),
        "meta_compliance": {
            "status": "✅ مناسب" if days >= 7 else "⚠️ دوره warm-up",
            "notes": [
                "هرگز بیش از ۲۰۰ پیام/روز به یک حساب جدید ارسال نکنید",
                "تاخیر حداقل ۴۵ ثانیه بین پیام‌ها رعایت کنید",
                "در هفته اول حداکثر ۵ پیام/روز ارسال کنید",
                "از ارسال یک پیام یکسان به چند نفر خودداری کنید (GPT این را حل می‌کند)",
            ],
        },
    }


@router.put("/{account_id}/limits")
async def update_account_limits(account_id: str, body: AccountLimitsUpdate, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    account.max_daily_absolute = body.max_daily_absolute
    account.incoming_ratio_multiplier = body.incoming_ratio_multiplier
    account.max_sends_per_minute = body.max_sends_per_minute
    await db.commit()
    return {"updated": True, "effective_limit": account.computed_daily_limit}


@router.get("/{account_id}/status")
async def check_account_status(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    state = await client.get_state()
    if state == "authorized":
        account.status = AccountStatus.active
    elif state == "blocked":
        account.status = AccountStatus.banned
    elif state == "notAuthorized":
        account.status = AccountStatus.disconnected
    await db.commit()
    return {"state": state, "status": account.status}


@router.get("/{account_id}/qr")
async def get_account_qr(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    # Degrade gracefully: a dead/unauthorized instance (or an open circuit breaker after
    # repeated failures) must NOT surface as a 500. Return a friendly Persian message.
    try:
        info = await client.get_qr_info()
    except Exception as e:
        msg = "دریافت QR برای این حساب ممکن نیست"
        if "403" in str(e):
            msg = "این حساب روی Green API مجاز/متصل نیست (خطای ۴۰۳)"
        elif "circuit" in str(e).lower() or "degraded" in str(e).lower():
            msg = "این حساب موقتاً پاسخ نمی‌دهد (اتصال instance را در Green API بررسی کنید)"
        return {"qr": "", "type": "error", "message": msg, "error": msg}
    qtype = info.get("type", "")
    message = info.get("message", "")
    # base64 PNG is only present when Green API is waiting for a scan (qrCode)
    return {"qr": message if qtype == "qrCode" else "", "type": qtype, "message": message}


@router.post("/{account_id}/reboot")
async def reboot_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.reboot()
    return {"rebooted": ok}


@router.post("/{account_id}/logout")
async def logout_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.logout()
    account.status = AccountStatus.disconnected
    await db.commit()
    return {"logged_out": ok}


@router.post("/{account_id}/apply-settings")
async def apply_account_settings(account_id: str, db: AsyncSession = Depends(get_db)):
    """Re-apply Green API settings (webhook + 15000ms queue send delay + proxy) for this account."""
    account = await _get_account(account_id, db)
    webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/{account.instance_id}"
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.set_webhook(webhook_url, delay_ms=15000)

    proxy_applied = False
    if account.proxy_enabled and account.proxy_host:
        proxy_applied = await client.set_proxy(
            account.proxy_host,
            account.proxy_port or 1080,
            account.proxy_login or "",
            account.proxy_password or "",
        )
    return {"applied": ok, "webhook_url": webhook_url, "delay_ms": 15000, "proxy_applied": proxy_applied}


class ProxyUpdate(BaseModel):
    proxy_host: str = ""
    proxy_port: int = 1080
    proxy_login: str = ""
    proxy_password: str = ""
    proxy_enabled: bool = False


@router.put("/{account_id}/proxy")
async def update_proxy(account_id: str, body: ProxyUpdate, db: AsyncSession = Depends(get_db)):
    """Set or remove a SOCKS5 proxy for a WhatsApp account."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    if body.proxy_enabled and body.proxy_host:
        account.proxy_host = body.proxy_host
        account.proxy_port = body.proxy_port
        account.proxy_login = body.proxy_login
        account.proxy_password = body.proxy_password
        account.proxy_enabled = True
        applied = await client.set_proxy(body.proxy_host, body.proxy_port, body.proxy_login, body.proxy_password)
    else:
        account.proxy_enabled = False
        account.proxy_host = None
        applied = await client.remove_proxy()
    await db.commit()
    return {"applied": applied, "proxy_enabled": account.proxy_enabled}


@router.get("/{account_id}/proxy")
async def get_proxy(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        proxy_url = await client.get_proxy()
    except Exception:
        proxy_url = None
    return {
        "proxy_enabled": account.proxy_enabled,
        "proxy_host": account.proxy_host,
        "proxy_port": account.proxy_port,
        "green_api_proxy_url": proxy_url,
    }


@router.get("/{account_id}/blocked-contacts")
async def get_blocked_contacts(account_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch blocked contacts from WhatsApp and sync to DB."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        blocked = await client.get_contacts_block()
    except Exception as e:
        raise HTTPException(502, f"Green API error: {e}")

    from app.models.wa_extras import WaBlockedContact
    from sqlalchemy import delete
    await db.execute(delete(WaBlockedContact).where(WaBlockedContact.account_id == uuid.UUID(account_id)))
    for b in blocked:
        phone = str(b.get("id", "")).split("@")[0] if isinstance(b, dict) else str(b).split("@")[0]
        if phone:
            db.add(WaBlockedContact(account_id=uuid.UUID(account_id), phone=phone))
    await db.commit()
    return {"count": len(blocked), "blocked": blocked}


@router.post("/{account_id}/set-default")
async def set_default_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """Set one account as default (used for single-account operations like checkWhatsapp)."""
    from sqlalchemy import update
    account = await _get_account(account_id, db)
    await db.execute(update(Account).values(is_default=False))
    account.is_default = True
    await db.commit()
    return {"default_account": str(account.id), "name": account.name}


class AccountRename(BaseModel):
    name: str


@router.put("/{account_id}/rename")
async def rename_account(account_id: str, body: AccountRename, db: AsyncSession = Depends(get_db)):
    """Change an account's display name."""
    account = await _get_account(account_id, db)
    new_name = (body.name or "").strip()[:200]
    if not new_name:
        raise HTTPException(400, "نام حساب نمی‌تواند خالی باشد")
    account.name = new_name
    await db.commit()
    return {"id": str(account.id), "name": account.name}


@router.get("/{account_id}/health")
async def account_health(account_id: str, db: AsyncSession = Depends(get_db)):
    """V13.2 — health score (0..1) + breakdown for smart send rotation."""
    from app.services.account_health import health_breakdown
    account = await _get_account(account_id, db)
    return {"account_id": str(account.id), "name": account.name, **await health_breakdown(account, db)}


@router.post("/{account_id}/check-whatsapp-bulk")
async def check_whatsapp_bulk(
    account_id: str,
    contact_ids: list[str],
    db: AsyncSession = Depends(get_db)
):
    """Batch-check whether contacts have WhatsApp using this account."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    from datetime import datetime
    results = []
    for cid in contact_ids:
        contact = await db.get(Contact, uuid.UUID(cid))
        if not contact:
            continue
        try:
            has_wa = await client.check_whatsapp(contact.phone)
            contact.has_whatsapp = has_wa
            contact.whatsapp_checked_at = datetime.utcnow()
            results.append({"id": cid, "phone": contact.phone, "has_whatsapp": has_wa})
        except Exception as e:
            results.append({"id": cid, "phone": contact.phone, "error": str(e)})
    await db.commit()
    return {"checked": len(results), "results": results}


@router.put("/{account_id}/auto-reply")
async def update_auto_reply(account_id: str, payload: AutoReplyUpdate, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    if payload.auto_reply_enabled is not None:
        account.auto_reply_enabled = payload.auto_reply_enabled
    if payload.auto_reply_message is not None:
        account.auto_reply_message = payload.auto_reply_message
    if payload.auto_reply_outside_hours is not None:
        account.auto_reply_outside_hours = payload.auto_reply_outside_hours
    if payload.warmup_enabled is not None:
        account.warmup_enabled = payload.warmup_enabled
    if payload.polling_enabled is not None:
        account.polling_enabled = payload.polling_enabled
    await db.commit()
    return {
        "auto_reply_enabled": account.auto_reply_enabled,
        "auto_reply_message": account.auto_reply_message,
        "auto_reply_outside_hours": account.auto_reply_outside_hours,
        "warmup_enabled": account.warmup_enabled,
        "polling_enabled": account.polling_enabled,
    }


@router.get("/{account_id}/queue")
async def get_account_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    queue = await client.show_messages_queue()
    return {"queue": queue, "count": len(queue) if isinstance(queue, list) else 0}


@router.delete("/{account_id}/queue")
async def clear_account_queue(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.clear_messages_queue()
    return {"cleared": ok}


@router.post("/{account_id}/send-typing")
async def send_typing(account_id: str, phone: str, seconds: int = 3, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.send_typing(phone, seconds)
    return {"typing_sent": ok}


@router.post("/{account_id}/messages/{message_id}/edit")
async def edit_message(account_id: str, message_id: str, phone: str, new_text: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.edit_message(phone, message_id, new_text)
    return {"edited": ok}


@router.delete("/{account_id}/messages/{message_id}")
async def delete_message(account_id: str, message_id: str, phone: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.delete_message(phone, message_id)
    return {"deleted": ok}


@router.post("/{account_id}/contacts/add")
async def add_contact_to_phonebook(account_id: str, phone: str, first_name: str, last_name: str = "", db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.add_contact(phone, first_name, last_name)
    return {"added": ok}


@router.post("/{account_id}/token/refresh")
async def refresh_api_token(account_id: str, db: AsyncSession = Depends(get_db)):
    """Generate a new API token. Old token stays valid ~1h. Update DB immediately."""
    account = await _get_account(account_id, db)
    client = GreenAPIClient(account.instance_id, account.api_token)
    new_token = await client.update_api_token()
    if new_token:
        account.api_token = new_token
        await db.commit()
    return {"new_token": new_token, "updated_in_db": bool(new_token)}


# ── V14 F17 — profile picture (multipart; ⚠️ 0.1/sec = one call per 10 seconds) ──
_PFP_DIR = "/app/.pfp_tmp"
_PFP_PROGRESS_KEY = "pfp_apply_progress"


@router.post("/profile-picture/apply-all")
async def apply_profile_picture_all(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """⭐ Set the SAME picture on every active account. Because of the 0.1/s limit this
    runs as a Celery task with a 10s gap between accounts. Poll the progress endpoint."""
    total = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    if not total:
        raise HTTPException(400, "هیچ حساب فعالی وجود ندارد")
    os.makedirs(_PFP_DIR, exist_ok=True)
    ext = (os.path.splitext(file.filename or "")[1] or ".jpg")
    path = os.path.join(_PFP_DIR, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as fh:
        fh.write(await file.read())
    from app.workers.tasks import task_apply_profile_picture_all
    task_apply_profile_picture_all.delay(path)
    return {"started": True, "total": len(total)}


@router.get("/profile-picture/apply-all/progress")
async def apply_profile_picture_progress():
    import json
    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        raw = await r.get(_PFP_PROGRESS_KEY)
        return json.loads(raw) if raw else {"done": 0, "total": 0, "finished": True}
    except Exception:
        return {"done": 0, "total": 0, "finished": True}


@router.post("/{account_id}/profile-picture")
async def set_profile_picture(account_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    data = await file.read()
    try:
        res = await GreenAPIClient(account.instance_id, account.api_token).set_profile_picture_upload(
            data, file.filename or "avatar.jpg")
    except Exception as e:
        _logger.error("setProfilePicture failed: %s", e)
        raise HTTPException(502, "تنظیم عکس پروفایل ناموفق بود")
    url_avatar = res.get("urlAvatar") if isinstance(res, dict) else None
    if url_avatar:
        account.profile_picture_url = url_avatar
        await db.commit()
    return {"ok": bool(res.get("setProfilePicture") if isinstance(res, dict) else res), "url_avatar": url_avatar}


# ── V15 Item 26 — managed auto warm-up toggle ───────────────────────────────
class WarmupToggle(BaseModel):
    enabled: bool


@router.post("/{account_id}/warmup")
async def set_auto_warmup(account_id: str, body: WarmupToggle, db: AsyncSession = Depends(get_db)):
    """V18 PART 2 — the «گرم‌سازی هوشمند» toggle now drives the V17 mesh.

    ON  → migrate off the legacy flag and create/activate a real `warmup_enrollment`
          (pre-flight: warming SetSettings, 24h cooldown, mutual-contact mesh handshake).
          If there aren't enough warm peers, the enrollment still holds and a Persian
          insufficient-peers notice is returned (nothing is sent to strangers).
    OFF → pause/disable the enrollment, stopping all mesh activity for the number.
    """
    account = await _get_account(account_id, db)
    # Enrollment is now the single source of truth — retire the legacy auto_warmup flag so
    # the old warm-up engine never double-warms an enrolled number.
    account.auto_warmup = False
    if body.enabled:
        from app.services.warmup_mesh_service import enroll_and_preflight
        result = await enroll_and_preflight(db, account)   # commits internally
        return {
            "warmup_enrolled": True,
            "state": result.get("state"),
            "notice": result.get("notice"),
            "peers": result.get("peers", []),
            "cooldown_hours": result.get("cooldown_hours"),
            "settings_applied": result.get("settings_applied"),
        }
    else:
        from app.services.warmup_mesh_service import disable_warmup
        result = await disable_warmup(db, account)          # commits internally
        return {"warmup_enrolled": False, "state": result.get("state")}


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    await db.delete(account)
    await db.commit()
    return {"success": True}
