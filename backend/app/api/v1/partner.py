"""V14 PART A — Green API Partner API (Features 1–6).

Create / delete / sync instances, the management/billing data, in-app QR, and
phone-code auth. Token safety: a partner or instance token is NEVER logged or
returned, except the unavoidable `qr_url` which is generated on demand and only
handed to the dashboard user.
"""
import re
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.config import settings
from app.models.account import Account, AccountStatus
from app.models.partner import PartnerInstanceLog
from app.services import green_partner
from app.services.green_api import GreenAPIClient
from app.services.partner_sync import sync_partner_instances
from app.services.capabilities import record_support
from app.utils.shamsi import to_shamsi

logger = logging.getLogger("afrakala.partner")
router = APIRouter(prefix="/partner", tags=["partner"])

WEBHOOK_BASE = f"{settings.webhook_base_url}/api/v1/webhook"


class CreateInstanceBody(BaseModel):
    name: str
    delay_ms: int = 15000


class AuthCodeBody(BaseModel):
    phone: str


def _require_configured():
    if not green_partner.is_configured():
        raise HTTPException(400, "توکن پارتنر تنظیم نشده است — آن را در فایل .env قرار دهید")


async def _account(account_id: str, db: AsyncSession) -> Account:
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "حساب یافت نشد")
    return acc


def _qr_url(instance_id: str, token: str) -> str:
    # NOTE: necessarily contains the token — generated on demand, never logged/stored.
    return f"https://qr.green-api.com/waInstance{instance_id}/{token}"


# ── Status (lets the UI disable Partner controls when unconfigured) ──────────
@router.get("/status")
async def partner_status():
    return {"configured": green_partner.is_configured()}


# ── FEATURE 4 (data) — list partner-managed instances + billing summary ─────
@router.get("/instances")
async def list_instances(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Account).where(Account.status != AccountStatus.deleted)
        .order_by(Account.created_at.desc())
    )).scalars().all()

    now = datetime.utcnow()
    active_count = 0
    total_days_this_month = 0
    items = []
    for a in rows:
        active = a.status == AccountStatus.active
        if active:
            active_count += 1
        # days active THIS month (best-effort from partner_created_at)
        days_this_month = 0
        if a.partner_created_at:
            start = a.partner_created_at if a.partner_created_at.month == now.month \
                and a.partner_created_at.year == now.year else now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            days_this_month = max(0, (now - start).days)
        total_days_this_month += days_this_month
        items.append({
            "id": str(a.id),
            "name": a.name,
            "phone": a.phone,
            "instance_id": a.instance_id,
            "status": a.status.value if hasattr(a.status, "value") else a.status,
            "is_orphaned": a.is_orphaned,
            "tariff": a.tariff,
            "created_via_partner": a.created_via_partner,
            "partner_created_at": to_shamsi(a.partner_created_at),
            "days_active": a.days_active,
            "days_this_month": days_this_month,
            "estimated_month_cost": (days_this_month * settings.partner_daily_rate)
            if settings.partner_daily_rate else None,
        })

    return {
        "configured": green_partner.is_configured(),
        "instances": items,
        "summary": {
            "active_count": active_count,
            "daily_rate": settings.partner_daily_rate,
            "total_days_this_month": total_days_this_month,
            # Do NOT invent a price when the rate is unknown (0).
            "estimated_month_cost": (total_days_this_month * settings.partner_daily_rate)
            if settings.partner_daily_rate else None,
        },
    }


# ── FEATURE 1 — createInstance ──────────────────────────────────────────────
@router.post("/instances")
async def create_instance(body: CreateInstanceBody, db: AsyncSession = Depends(get_db)):
    _require_configured()
    payload = {
        "name": body.name,
        # Bootstrap with the id-less base URL; we set the correct per-instance URL below.
        "webhookUrl": f"{WEBHOOK_BASE}/",
        "webhookUrlToken": "",
        "delaySendMessagesMilliseconds": body.delay_ms,
        "markIncomingMessagesReaded": "no",
        "markIncomingMessagesReadedOnReply": "no",
        "outgoingWebhook": "yes",
        "outgoingMessageWebhook": "yes",
        "outgoingAPIMessageWebhook": "yes",
        "incomingWebhook": "yes",
        "stateWebhook": "yes",
        "deviceWebhook": "no",
        "keepOnlineStatus": "no",
        "pollMessageWebhook": "yes",
        "incomingBlockWebhook": "yes",
        "incomingCallWebhook": "yes",
        "editedMessageWebhook": "yes",
        "deletedMessageWebhook": "yes",
    }
    try:
        result = await green_partner.create_instance(payload)
    except Exception as e:
        logger.error("createInstance failed: %s", e)
        raise HTTPException(502, "ساخت شماره ناموفق بود")

    id_instance = result.get("idInstance")
    api_token = result.get("apiTokenInstance")
    if not id_instance or not api_token:
        raise HTTPException(502, "پاسخ نامعتبر از Green API هنگام ساخت شماره")
    id_str = str(id_instance)

    # Immediately fix the webhook URL to include the new idInstance.
    try:
        client = GreenAPIClient(id_str, api_token)
        await client.set_webhook(f"{WEBHOOK_BASE}/{id_str}", delay_ms=body.delay_ms)
    except Exception as e:
        logger.warning("post-create setSettings failed for %s: %s", id_str, e)

    account = Account(
        name=body.name,
        instance_id=id_str,
        api_token=api_token,
        status=AccountStatus.pending,
        created_via_partner=True,
        partner_created_at=datetime.utcnow(),
        days_active=0,
    )
    db.add(account)
    db.add(PartnerInstanceLog(id_instance=int(id_instance), action="created", detail=body.name))
    await db.commit()
    await db.refresh(account)
    await record_support(db, "createInstance", True, 200)

    return {
        "id": str(account.id),
        "id_instance": id_instance,
        "qr_url": _qr_url(id_str, api_token),
    }


# ── FEATURE 2 — deleteInstanceAccount ───────────────────────────────────────
@router.delete("/instances/{id_instance}")
async def delete_instance(id_instance: int, db: AsyncSession = Depends(get_db)):
    _require_configured()
    id_str = str(id_instance)
    account = (await db.execute(
        select(Account).where(Account.instance_id == id_str)
    )).scalar_one_or_none()

    # If authorized, log out FIRST (never auto-logout is only for auth-code flow;
    # here deletion is explicit so logging out the session is the safe recommended step).
    if account and account.status == AccountStatus.active:
        try:
            await GreenAPIClient(id_str, account.api_token).logout()
        except Exception as e:
            logger.warning("pre-delete logout failed for %s: %s", id_str, e)

    try:
        result = await green_partner.delete_instance_account(id_instance)
    except Exception as e:
        logger.error("deleteInstanceAccount failed: %s", e)
        raise HTTPException(502, "حذف شماره ناموفق بود")

    # {"code":404} already gone → treat as success. {"code":401} → bad token.
    code = result.get("code") if isinstance(result, dict) else None
    if code == 401:
        raise HTTPException(401, "توکن پارتنر نامعتبر است")

    if account:
        account.status = AccountStatus.deleted
        db.add(PartnerInstanceLog(id_instance=id_instance, action="deleted", detail=account.name))
        await db.commit()
    return {"deleted": True}


# ── FEATURE 3 — getInstances sync ───────────────────────────────────────────
@router.post("/sync")
async def sync_now(db: AsyncSession = Depends(get_db)):
    _require_configured()
    try:
        counts = await sync_partner_instances(db)
    except Exception as e:
        logger.error("partner sync failed: %s", e)
        raise HTTPException(502, "همگام‌سازی ناموفق بود")
    return {"ok": True, **counts}


# ── FEATURE 5 — in-app QR ───────────────────────────────────────────────────
@router.get("/instances/{account_id}/qr")
async def instance_qr(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _account(account_id, db)
    return {"qr_url": _qr_url(account.instance_id, account.api_token)}


# ── FEATURE 5/6 — poll instance state (drives modal auto-close) ─────────────
@router.get("/instances/{account_id}/state")
async def instance_state(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await _account(account_id, db)
    try:
        state = await GreenAPIClient(account.instance_id, account.api_token).get_state()
    except Exception as e:
        logger.warning("get_state failed for %s: %s", account.instance_id, e)
        return {"state": "unknown"}
    # Reflect an authorized instance locally so the list updates.
    if state == "authorized" and account.status != AccountStatus.active:
        account.reconnected_at = datetime.utcnow()  # V38 — anchor 24h post-reconnect TC rest
        account.status = AccountStatus.active
        await db.commit()
    return {"state": state, "status": account.status.value if hasattr(account.status, "value") else account.status}


# ── FEATURE 6 — phone-code auth ─────────────────────────────────────────────
@router.post("/instances/{account_id}/auth-code")
async def request_auth_code(account_id: str, body: AuthCodeBody, db: AsyncSession = Depends(get_db)):
    account = await _account(account_id, db)
    phone = re.sub(r"\D", "", body.phone or "")
    # International, no +, no 00, digits only. Reject anything implausible.
    if not (10 <= len(phone) <= 15):
        raise HTTPException(400, "شماره نامعتبر است — فقط رقم، بین‌المللی و بدون + یا 00 (مثال: 989122270261)")

    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        state = await client.get_state()
    except Exception:
        state = "unknown"
    if state == "authorized":
        raise HTTPException(409, "این شماره از قبل متصل است — برای اتصال مجدد ابتدا «خروج از حساب» را بزنید")

    try:
        result = await client.get_auth_code(phone)
    except Exception as e:
        logger.error("getAuthorizationCode failed for %s: %s", account.instance_id, e)
        raise HTTPException(502, "دریافت کد ناموفق بود — کمی بعد دوباره تلاش کنید")

    code = result.get("code") if isinstance(result, dict) else None
    if not code:
        raise HTTPException(502, "کد دریافت نشد — مطمئن شوید شماره صحیح و instance آماده است")
    # Code is valid ~2.5 minutes; the UI shows a countdown.
    return {"code": code, "expires_in_seconds": 150}


# ── PART G — capability registry (method-support table) ─────────────────────
@router.get("/capabilities")
async def capabilities(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT method, supported, last_status_code, last_checked, note "
        "FROM method_support ORDER BY method"
    ))).mappings().all()
    return [
        {
            "method": r["method"],
            "supported": r["supported"],
            "last_status_code": r["last_status_code"],
            "last_checked": to_shamsi(r["last_checked"]),
            "note": r["note"],
        }
        for r in rows
    ]
