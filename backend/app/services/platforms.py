"""TG PART 1 — platform abstraction shared by WhatsApp and Telegram.

Two platforms flow through the same Green API gateway but differ in chatId format, pacing,
message limits, and partner credentials. This module centralizes those differences so the
rest of the codebase branches on `platform` via helpers instead of scattering
`@g.us`/`@c.us` string checks (which are WRONG for Telegram).

CRITICAL: the WhatsApp and Telegram partner keys are DISTINCT credentials and are never
conflated — `partner_credentials(platform)` is the single place that maps a platform to its
own key + API base.
"""
from __future__ import annotations
import re

from app.config import settings

PLATFORM_WHATSAPP = "whatsapp"
PLATFORM_TELEGRAM = "telegram"
PLATFORMS = (PLATFORM_WHATSAPP, PLATFORM_TELEGRAM)

# ── Telegram-specific constants (kept SEPARATE from the WhatsApp send delay) ──
TELEGRAM_MESSAGE_MAX_CHARS = 4096          # Telegram's own SendMessage cap (WA is far higher)
TELEGRAM_NEW_ACCOUNT_GATE_HOURS = 48       # no outbound to non-contacts in the first 48h
# 10–15s between sends is Telegram support guidance — NOT the WhatsApp 45–110s constant.
TELEGRAM_MIN_DELAY_SECONDS = 10
TELEGRAM_MAX_DELAY_SECONDS = 15

# Telegram's richer typingType enum (WhatsApp only had text/recording).
TELEGRAM_TYPING_TYPES = (
    "text", "record_voice_note", "upload_voice_note", "record_video_note",
    "upload_video_note", "record_video", "upload_video", "upload_photo",
    "upload_document", "choose_sticker", "choose_location", "choose_contact",
)

_INT_RE = re.compile(r"^-?\d+$")


def normalize_platform(platform: str | None) -> str:
    """Coerce any input to a known platform; default to WhatsApp (the existing behavior)."""
    p = (platform or "").strip().lower()
    return p if p in PLATFORMS else PLATFORM_WHATSAPP


def platform_from_type_instance(type_instance: str | None) -> str:
    """Map a webhook's instanceData.typeInstance to our platform discriminator.
    Telegram webhooks carry typeInstance='telegram'; WhatsApp is anything else."""
    return PLATFORM_TELEGRAM if (type_instance or "").strip().lower() == "telegram" \
        else PLATFORM_WHATSAPP


def is_group_chat_id(chat_id: str | None, platform: str = PLATFORM_WHATSAPP) -> bool:
    """True if `chat_id` is a GROUP chat.

    WhatsApp: ends with '@g.us'.
    Telegram: the string represents a NEGATIVE number, e.g. '-10000000000000'.
    """
    if not chat_id:
        return False
    s = str(chat_id).strip()
    if normalize_platform(platform) == PLATFORM_TELEGRAM:
        return bool(_INT_RE.match(s)) and s.startswith("-")
    return s.endswith("@g.us")


def is_private_chat_id(chat_id: str | None, platform: str = PLATFORM_WHATSAPP) -> bool:
    """True if `chat_id` is a PRIVATE chat.

    WhatsApp: ends with '@c.us'.
    Telegram: a POSITIVE number, e.g. '10000000' (the '<phone>@c.us' backward-compat form is
    also accepted, since Green API still honors it for Telegram SendMessage).
    """
    if not chat_id:
        return False
    s = str(chat_id).strip()
    if normalize_platform(platform) == PLATFORM_TELEGRAM:
        if s.endswith("@c.us"):
            return True
        return bool(_INT_RE.match(s)) and not s.startswith("-")
    return s.endswith("@c.us")


def partner_credentials(platform: str) -> tuple[str, str]:
    """Return (partner_token, partner_api_url) for `platform`. This is the ONLY place a
    platform is mapped to its partner credentials, guaranteeing WhatsApp and Telegram keys
    are never conflated. Raises if the requested platform's key is not configured."""
    p = normalize_platform(platform)
    if p == PLATFORM_TELEGRAM:
        token = settings.green_partner_token_telegram
        url = settings.green_partner_api_url_telegram
    else:
        token = settings.green_partner_token
        url = settings.green_partner_api_url
    return token, url


def telegram_delay_seconds() -> tuple[int, int]:
    """Telegram-specific (min, max) send pacing — always distinct from the WhatsApp delay."""
    lo = settings.telegram_min_delay_seconds or TELEGRAM_MIN_DELAY_SECONDS
    hi = settings.telegram_max_delay_seconds or TELEGRAM_MAX_DELAY_SECONDS
    return lo, hi


def summarize_by_platform(accounts) -> dict:
    """Pure: per-platform breakdown of accounts (count + today's sent/received). Powers the
    platform-aware reporting so WhatsApp and Telegram are reported side-by-side, not merged."""
    out = {p: {"count": 0, "sent_today": 0, "received_today": 0, "active": 0}
           for p in PLATFORMS}
    for a in accounts:
        p = normalize_platform(getattr(a, "platform", PLATFORM_WHATSAPP))
        out[p]["count"] += 1
        out[p]["sent_today"] += int(getattr(a, "sent_today", 0) or 0)
        out[p]["received_today"] += int(getattr(a, "received_today", 0) or 0)
        if str(getattr(getattr(a, "status", None), "value", getattr(a, "status", ""))) == "active":
            out[p]["active"] += 1
    return out
