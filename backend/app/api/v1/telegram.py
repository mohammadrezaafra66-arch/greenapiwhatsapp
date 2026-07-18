"""TG PART 2 — Telegram instance connect + authorization endpoints.

A SEPARATE flow from the WhatsApp create-instance path: it stores platform='telegram' with
the Telegram partner API host, drives QR (preferred) or code+password (fallback) auth, polls
state to 'authorized' (stamping authorized_at for the 48h gate), and offers a self-test send.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from app.services import telegram_service as tg
from app.services.platforms import PLATFORM_TELEGRAM

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _tg_client(account: Account) -> GreenAPIClient:
    return GreenAPIClient(account.instance_id, account.api_token,
                          platform=PLATFORM_TELEGRAM,
                          api_host=account.api_host or settings.green_partner_api_url_telegram)


async def _get_tg_account(account_id: str, db: AsyncSession) -> Account:
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    if (acc.platform or "whatsapp") != PLATFORM_TELEGRAM:
        raise HTTPException(400, "این اکانت تلگرام نیست")
    return acc


class TelegramCreate(BaseModel):
    name: str
    instance_id: str
    api_token: str
    api_host: str | None = None    # default: the Telegram partner API base


@router.post("/accounts")
async def create_telegram_account(body: TelegramCreate, db: AsyncSession = Depends(get_db)):
    """Create a Telegram instance (platform='telegram') using the Telegram partner project.
    Distinct from the WhatsApp create flow; never uses the WhatsApp partner key."""
    name = (body.name or "").strip()
    instance_id = (body.instance_id or "").strip()
    api_token = (body.api_token or "").strip()
    if not instance_id or not api_token:
        raise HTTPException(400, "شناسه instance و توکن اتصال هر دو لازم است")
    if not name:
        name = instance_id
    existing = (await db.execute(
        select(Account).where(Account.instance_id == instance_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "این شناسه instance قبلاً ثبت شده است")
    api_host = (body.api_host or settings.green_partner_api_url_telegram or "").strip() or None
    account = Account(name=name, instance_id=instance_id, api_token=api_token,
                      platform=PLATFORM_TELEGRAM, api_host=api_host,
                      status=AccountStatus.pending)
    db.add(account)
    await db.commit()
    await db.refresh(account)

    # Bind the webhook (webhook-only; polling never enabled). Best-effort.
    try:
        webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/{instance_id}"
        await _tg_client(account).set_webhook(webhook_url, delay_ms=15000)
    except Exception as e:
        print(f"Warning: Could not set Telegram webhook: {e}")

    return {"id": str(account.id), "name": account.name, "platform": account.platform,
            "status": account.status}


@router.get("/qr-notice")
async def qr_notice():
    """Telegram-specific anti-ban notice for the QR/auth screen (NOT the WhatsApp wording)."""
    return {"notice": tg.TELEGRAM_QR_NOTICE, "link_hint": tg.TELEGRAM_AUTH_LINK_HINT,
            "preferred": "qr"}


@router.get("/accounts/{account_id}/qr")
async def telegram_qr(account_id: str, db: AsyncSession = Depends(get_db)):
    """Preferred auth path — QR code. Returns the base64 PNG when Green API is awaiting a scan."""
    acc = await _get_tg_account(account_id, db)
    try:
        info = await _tg_client(acc).get_qr_info()
    except Exception as e:
        msg = "دریافت QR برای این حساب ممکن نیست"
        if "403" in str(e):
            msg = "این حساب روی Green API مجاز/متصل نیست (خطای ۴۰۳)"
        return {"qr": "", "type": "error", "message": msg}
    qtype = info.get("type", "")
    return {"qr": info.get("message", "") if qtype == "qrCode" else "", "type": qtype,
            "message": info.get("message", "")}


class AuthStart(BaseModel):
    phone: str


class AuthCode(BaseModel):
    code: str


class AuthPassword(BaseModel):
    password: str


@router.post("/accounts/{account_id}/auth/start")
async def telegram_auth_start(account_id: str, body: AuthStart, db: AsyncSession = Depends(get_db)):
    """Fallback auth path — code-based login (may be unstable per Telegram; QR preferred)."""
    acc = await _get_tg_account(account_id, db)
    return await _tg_client(acc).start_authorization(body.phone)


@router.post("/accounts/{account_id}/auth/code")
async def telegram_auth_code(account_id: str, body: AuthCode, db: AsyncSession = Depends(get_db)):
    acc = await _get_tg_account(account_id, db)
    return await _tg_client(acc).send_authorization_code(body.code)


@router.post("/accounts/{account_id}/auth/password")
async def telegram_auth_password(account_id: str, body: AuthPassword,
                                 db: AsyncSession = Depends(get_db)):
    """Submit the 2FA cloud password (only for accounts with 2FA enabled)."""
    acc = await _get_tg_account(account_id, db)
    return await _tg_client(acc).send_authorization_password(body.password)


@router.get("/accounts/{account_id}/state")
async def telegram_state(account_id: str, db: AsyncSession = Depends(get_db)):
    """Poll the instance state; on 'authorized' stamp authorized_at (48h-gate anchor) and
    surface Telegram's suspended/blocked states."""
    acc = await _get_tg_account(account_id, db)
    try:
        state = await _tg_client(acc).get_state()
    except Exception as e:
        return {"state": "error", "message": str(e)[:200]}
    tg.apply_state(acc, state)
    await db.commit()
    return {"state": state, "status": acc.status,
            "authorized_at": acc.authorized_at.isoformat() if acc.authorized_at else None}


class SelfTest(BaseModel):
    chat_id: str | None = None    # defaults to sending to the instance's own wid


@router.post("/accounts/{account_id}/send-test")
async def telegram_send_test(account_id: str, body: SelfTest, db: AsyncSession = Depends(get_db)):
    """Send a test message (to yourself by default) to validate the whole pipe end-to-end."""
    acc = await _get_tg_account(account_id, db)
    client = _tg_client(acc)
    target = (body.chat_id or "").strip()
    if not target:
        # Resolve the instance's own chat via getWaSettings/getAccountSettings wid.
        try:
            info = await client.get_account_settings()
            wid = info.get("wid") or info.get("phone") or ""
            target = str(wid).split("@")[0]
        except Exception:
            raise HTTPException(400, "chat_id مقصد لازم است")
    msg_id = await client.send_message(target, "پیام تست افراکالا ✅")
    return {"sent": bool(msg_id), "id_message": msg_id, "target": target}
