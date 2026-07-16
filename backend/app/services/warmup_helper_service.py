"""V25 PART 1 — "human helpers" warm-up assist: service + pure helpers.

The user keeps a SMALL, capped list (≤25) of REAL known people who already have the user's
number saved. When the single toggle is ON, the main warm account SLOWLY asks each helper to
send a friendly WhatsApp message to a NEW cold number, giving it genuine human incoming
traffic. This module holds:

  • the hard 25-cap enforcement (adding a 26th is rejected with a Persian error),
  • CRUD over helpers + the single global toggle,
  • the pure message builders (ask / reminder / thank-you) and the wa.me link builder,
  • the pure slow-send rate gate (waking hours + jittered gap between asks).

Everything pure is `rng`/`now`-injectable so the anti-ban pacing is unit-tested without the
network, a DB, or the clock. The async orchestration lives in warmup_helper_engine.py.
"""
from __future__ import annotations
import random
import re
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperConfig
from app.services.warmup_scheduler import in_active_hours, to_tehran  # 09:00–21:00 Tehran
from app.services.warmup_state import DEFAULT_WARMUP_CONFIG

# ── Hard anti-spam boundary ──────────────────────────────────────────────────
# The list is a FIXED, tiny set of known contacts — NEVER auto-imported, never > 25.
MAX_ACTIVE_HELPERS = 25
HELPER_CAP_NOTICE = (
    "حداکثر ۲۵ فرد کمک‌کننده مجاز است. برای افزودن فرد جدید، ابتدا یکی از افراد فعلی را "
    "غیرفعال یا حذف کنید."
)

# ── Slow-send rate gate (protect the main account — MANDATORY) ───────────────
# No more than ~1 helper-ask every few minutes, with randomized jitter, waking hours only.
# Sends are spread; the engine sends AT MOST one ask/reminder per gate slot.
HELPER_ASK_MIN_GAP_SECONDS = 180   # 3 min floor between two helper-asks from the main account
HELPER_ASK_MAX_GAP_SECONDS = 420   # 7 min ceiling — randomized within [min, max]
# A helper is never re-asked for the same cold number more than: 1 ask + 1 reminder.
REMINDER_AFTER_HOURS = 1

# Task lifecycle statuses.
STATUS_PENDING = "pending"
STATUS_ASKED = "asked"
STATUS_REMINDED = "reminded"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"


class HelperCapError(Exception):
    """Raised when adding a helper would exceed the hard 25-active cap."""


# ── pure: wa.me link + digit extraction ──────────────────────────────────────
def wa_me_digits(phone: str | None) -> str:
    """Reduce a phone to the bare digits used in a wa.me click-to-chat link (no +, spaces,
    or @c.us suffix). Persian/Arabic digits are normalized to ASCII first."""
    if not phone:
        return ""
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return re.sub(r"\D", "", str(phone).translate(trans).split("@")[0])


def wa_me_link(phone: str | None) -> str | None:
    """Build a https://wa.me/<digits> one-tap link from a cold number's real phone.
    Returns None when no usable digits exist (caller must resolve the phone first)."""
    d = wa_me_digits(phone)
    return f"https://wa.me/{d}" if d else None


# ── pure: Persian message builders ───────────────────────────────────────────
# A short copy/paste suggestion the helper can send to the new number.
SUGGESTED_TEXT = "سلام، خوبی؟"


def build_ask_message(name: str | None, link: str | None,
                      suggested: str = SUGGESTED_TEXT) -> str:
    """The friendly Persian request the main account sends to a helper: a short ask, the
    one-tap wa.me link for the new number, and a copy/paste suggested message. Never
    contains the internal account number/label — only the public wa.me link."""
    who = (name or "").strip()
    greeting = f"سلام {who}،" if who else "سلام،"
    lines = [
        f"{greeting} لطف می‌کنی به این شماره‌ی جدید ما یک پیام کوتاه بدی؟ داریم فعالش می‌کنیم 🙏",
    ]
    if link:
        lines.append(f"لینک مستقیم (یک لمس): {link}")
    lines.append(f"می‌تونی همین رو بفرستی: «{suggested}»")
    return "\n".join(lines)


def build_reminder_message(name: str | None, link: str | None) -> str:
    """The single, gentle Persian reminder sent once if the helper hasn't acted after 1h."""
    who = (name or "").strip()
    greeting = f"سلام {who} جان،" if who else "سلام،"
    lines = [f"{greeting} اگر فرصت کردی همون پیام کوتاه رو برای شماره‌ی جدیدمون بفرست، ممنون می‌شم 🌹"]
    if link:
        lines.append(f"لینک: {link}")
    return "\n".join(lines)


def build_thankyou_message(name: str | None) -> str:
    """The automatic Persian thank-you sent when the helper's greeting is detected."""
    who = (name or "").strip()
    return f"ممنون از لطفت {who} 🙏".replace("لطفت  ", "لطفت ").strip() if who else "ممنون از لطفت 🙏"


# ── pure: slow-send rate gate ────────────────────────────────────────────────
def next_ask_at(now: datetime, rng: random.Random | None = None) -> datetime:
    """The earliest time the NEXT helper-ask may be sent: now + a randomized gap in
    [MIN, MAX] seconds. Jittered so asks never fire on a fixed cadence. Naive UTC in/out."""
    r = rng or random
    gap = r.uniform(HELPER_ASK_MIN_GAP_SECONDS, HELPER_ASK_MAX_GAP_SECONDS)
    return now + timedelta(seconds=gap)


def can_ask_now(now: datetime, gate_next_ask_at: datetime | None,
                cfg=DEFAULT_WARMUP_CONFIG) -> bool:
    """True only when BOTH: we're inside waking hours (09:00–21:00 Tehran) AND the jittered
    rate gate has elapsed (gate is None → first ask allowed). The single guard that keeps the
    main account from blasting helpers — even with 25 helpers × many cold numbers."""
    if not in_active_hours(now, cfg):
        return False
    if gate_next_ask_at is None:
        return True
    return now >= gate_next_ask_at


# ── DB: config (single row) ──────────────────────────────────────────────────
async def get_config(db) -> WarmupHelperConfig:
    """Fetch (or lazily create) the single global config row."""
    cfg = (await db.execute(select(WarmupHelperConfig).limit(1))).scalar_one_or_none()
    if cfg is None:
        cfg = WarmupHelperConfig(is_enabled=False)
        db.add(cfg)
        await db.flush()
    return cfg


async def set_enabled(db, enabled: bool) -> WarmupHelperConfig:
    """Flip the one toggle on/off (default OFF). Commits."""
    cfg = await get_config(db)
    cfg.is_enabled = bool(enabled)
    await db.commit()
    return cfg


# ── DB: helper CRUD (with the hard 25-cap) ───────────────────────────────────
async def count_active_helpers(db) -> int:
    return int((await db.execute(
        select(func.count()).select_from(WarmupHelper).where(WarmupHelper.is_active.is_(True))
    )).scalar() or 0)


async def list_helpers(db) -> list[WarmupHelper]:
    return list((await db.execute(
        select(WarmupHelper).order_by(WarmupHelper.created_at)
    )).scalars().all())


async def add_helper(db, name: str, phone: str, is_active: bool = True) -> WarmupHelper:
    """Add ONE known helper. Enforces the hard 25-ACTIVE cap: adding a 26th active helper
    raises HelperCapError (rejected with a Persian message at the API). Never auto-imports."""
    name = (name or "").strip()
    digits = wa_me_digits(phone)
    if not name:
        raise ValueError("نام فرد کمک‌کننده لازم است")
    if not digits:
        raise ValueError("شماره‌ی معتبر لازم است")
    if is_active and await count_active_helpers(db) >= MAX_ACTIVE_HELPERS:
        raise HelperCapError(HELPER_CAP_NOTICE)
    helper = WarmupHelper(name=name, phone=digits, is_active=bool(is_active))
    db.add(helper)
    await db.commit()
    await db.refresh(helper)
    return helper


async def update_helper(db, helper_id, *, name=None, phone=None, is_active=None) -> WarmupHelper:
    """Edit a helper. Re-activating a helper is also gated by the 25-cap."""
    helper = await db.get(WarmupHelper, helper_id)
    if helper is None:
        raise ValueError("فرد کمک‌کننده یافت نشد")
    if is_active is True and not helper.is_active:
        if await count_active_helpers(db) >= MAX_ACTIVE_HELPERS:
            raise HelperCapError(HELPER_CAP_NOTICE)
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("نام فرد کمک‌کننده لازم است")
        helper.name = name
    if phone is not None:
        digits = wa_me_digits(phone)
        if not digits:
            raise ValueError("شماره‌ی معتبر لازم است")
        helper.phone = digits
    if is_active is not None:
        helper.is_active = bool(is_active)
    await db.commit()
    await db.refresh(helper)
    return helper


async def delete_helper(db, helper_id) -> bool:
    helper = await db.get(WarmupHelper, helper_id)
    if helper is None:
        return False
    await db.delete(helper)
    await db.commit()
    return True
