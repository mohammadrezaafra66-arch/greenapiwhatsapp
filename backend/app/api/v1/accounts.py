from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.services.green_api import GreenAPIClient
from app.config import settings
import uuid

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
    result = await db.execute(select(Account).order_by(Account.created_at.desc()))
    accounts = result.scalars().all()
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
    info = await client.get_qr_info()
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


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    await db.delete(account)
    await db.commit()
    return {"success": True}
