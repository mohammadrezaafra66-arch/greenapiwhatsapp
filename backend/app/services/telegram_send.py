"""TG PART 3 / PART 6 — Telegram send primitives (platform-specific).

Pure, testable building blocks reused by campaigns (PART 3) and group auto-reply (PART 4):
  • split_message  — respect Telegram's 4096-char cap without changing meaning (never
    silently truncate; split on natural boundaries);
  • telegram_can_send_to — the hard 48h non-contact gate (PART 6's shared gate);
  • resolve_chat_id — CheckAccount → cache so a phone resolves to its real chatId once;
  • telegram_send_delay — the Telegram-specific 10–15s jittered pacing (never the WA delay).
"""
from __future__ import annotations
import random
from datetime import datetime, timedelta

from app.services.platforms import (
    TELEGRAM_MESSAGE_MAX_CHARS, TELEGRAM_NEW_ACCOUNT_GATE_HOURS, telegram_delay_seconds,
)


# ── message splitting (4096-char cap) ────────────────────────────────────────
def split_message(text: str, limit: int = TELEGRAM_MESSAGE_MAX_CHARS) -> list[str]:
    """Split `text` into chunks each <= limit chars, preferring paragraph/line/space
    boundaries so meaning isn't cut mid-word. Never truncates; returns >= 1 chunk."""
    if text is None:
        return []
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        # Prefer to break at the last paragraph, then newline, then space in the window.
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut <= 0:
            cut = limit                       # no natural boundary → hard split at the cap
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if c]


# ── 48h non-contact gate (PART 6 shared gate) ────────────────────────────────
def telegram_can_send_to(authorized_at: datetime | None, is_existing_contact: bool,
                         now: datetime | None = None,
                         gate_hours: int = TELEGRAM_NEW_ACCOUNT_GATE_HOURS) -> bool:
    """False if the instance is within `gate_hours` of authorization AND the target is NOT an
    existing contact/prior conversation. Sending to strangers in the first 48h is a known
    Telegram spam-lock trigger. An established contact is always allowed."""
    if is_existing_contact:
        return True
    if authorized_at is None:
        # Unknown authorization time → be safe and block non-contact sends.
        return False
    now = now or datetime.utcnow()
    return now >= authorized_at + timedelta(hours=gate_hours)


def hours_until_gate_open(authorized_at: datetime | None, now: datetime | None = None,
                          gate_hours: int = TELEGRAM_NEW_ACCOUNT_GATE_HOURS) -> float:
    """Hours remaining before the 48h non-contact gate opens (0 if already open)."""
    if authorized_at is None:
        return float(gate_hours)
    now = now or datetime.utcnow()
    opens = authorized_at + timedelta(hours=gate_hours)
    return max(0.0, (opens - now).total_seconds() / 3600.0)


# ── Telegram-specific pacing (NEVER the WhatsApp delay) ──────────────────────
def telegram_send_delay(rng: random.Random | None = None) -> float:
    """A jittered 10–15s pause between two Telegram sends from the same instance."""
    r = rng or random
    lo, hi = telegram_delay_seconds()
    return r.uniform(lo, hi)


# ── chatId resolution + cache ────────────────────────────────────────────────
async def resolve_chat_id(db, client, phone: str) -> tuple[str | None, bool]:
    """Resolve a phone to its Telegram chatId via CheckAccount, caching the result per
    (instance_id, phone). Returns (chat_id, exist). On a resolution error returns (None, False).
    The cached chatId is what SendMessage should target (Green API recommends this over the
    '<phone>@c.us' fallback)."""
    from sqlalchemy import select
    from app.models.telegram import TelegramChatIdCache

    inst = client.instance_id
    cached = (await db.execute(
        select(TelegramChatIdCache).where(
            TelegramChatIdCache.instance_id == inst,
            TelegramChatIdCache.phone == str(phone),
        )
    )).scalar_one_or_none()
    if cached:
        return (cached.chat_id if cached.exist else None), bool(cached.exist)

    try:
        res = await client.check_account(phone)
    except Exception:
        return None, False
    exist = bool(res.get("exist", False))
    chat_id = str(res.get("chatId") or "") if exist else ""
    row = TelegramChatIdCache(instance_id=inst, phone=str(phone),
                              chat_id=chat_id or "", exist=exist)
    db.add(row)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
    return (chat_id or None), exist
