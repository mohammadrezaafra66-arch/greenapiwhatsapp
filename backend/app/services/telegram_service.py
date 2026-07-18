"""TG PART 2 — Telegram instance connect/authorize helpers.

Pure state-mapping (testable without a DB/network) + the Telegram-specific anti-ban notice
strings shown on the QR/auth screen (distinct from the WhatsApp V22 wording).
"""
from __future__ import annotations
from datetime import datetime

from app.models.account import AccountStatus

# Telegram-specific QR/auth-screen anti-ban notice (Persian, RTL). NOT the WhatsApp text.
TELEGRAM_QR_NOTICE = [
    "۱. اکانت را ابتدا در اپ تلگرام به‌صورت عادی چند روز استفاده کنید، سپس این کد را اسکن کنید.",
    "۲. در ۴۸ ساعت اول بعد از اتصال، این اکانت به هیچ غریبه‌ای پیام نمی‌فرستد — این محدودیت خودکار و برای محافظت از اکانت است.",
    "۳. فاصله‌ی ارسال پیام در تلگرام حداقل ۱۰ تا ۱۵ ثانیه است — سریع‌تر ارسال نکنید.",
    "۴. اگر روش کد+رمز را انتخاب کنید، ممکن است طبق تلگرام ناپایدار باشد — روش QR ترجیح دارد.",
]

TELEGRAM_AUTH_LINK_HINT = "در اپ تلگرام: Settings → Devices → Link Desktop Device را باز کنید و این کد را اسکن کنید."


def map_state_to_status(state: str | None) -> AccountStatus | None:
    """Map a Green API stateInstance string to our AccountStatus. Returns None for transient
    states (starting/sleep) so we don't overwrite a good status with a blip."""
    s = (state or "").strip()
    if s == "authorized":
        return AccountStatus.active
    if s == "blocked":
        return AccountStatus.banned
    if s == "suspended":                 # TG — spam restriction (Green API 2026)
        return AccountStatus.suspended
    if s == "notAuthorized":
        return AccountStatus.disconnected
    return None


def apply_state(account, state: str | None, now: datetime | None = None) -> AccountStatus | None:
    """Apply a Green API state to an account row: set status, and stamp authorized_at the
    FIRST time it becomes authorized (drives the PART 6 48h non-contact gate). Returns the
    new status, or None if the state was transient/ignored."""
    now = now or datetime.utcnow()
    status = map_state_to_status(state)
    if status is None:
        return None
    account.status = status
    if status == AccountStatus.active and not getattr(account, "authorized_at", None):
        account.authorized_at = now
    return status
