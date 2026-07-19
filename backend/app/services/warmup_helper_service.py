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

# ── Soft anti-spam boundary (V28: NO hard cap) ───────────────────────────────
# V25 hard-capped the list at 25. V28 removes that cap by design — the user chose it — and
# replaces it with a NON-BLOCKING soft-warning banner once a sender's list grows past a
# configurable threshold (default 30). The REAL safety rail is PACING (see warmup_helper_engine
# + V27's health gate/pacer), which makes a large list simply take longer, never a burst.
# Kept for backward-compat imports only (no longer enforced as a hard limit):
MAX_ACTIVE_HELPERS = 25
HELPER_CAP_NOTICE = (
    "حداکثر ۲۵ فرد کمک‌کننده مجاز است. برای افزودن فرد جدید، ابتدا یکی از افراد فعلی را "
    "غیرفعال یا حذف کنید."
)
DEFAULT_SOFT_WARNING_THRESHOLD = 30


def soft_warning_notice(count: int, threshold: int = DEFAULT_SOFT_WARNING_THRESHOLD) -> str | None:
    """PURE. The non-blocking Persian banner shown when a sender's contact list is large, or
    None when it's within the normal range. NEVER blocks — informational only."""
    if int(count) <= int(threshold):
        return None
    return (
        "تعداد مخاطبان این فرستنده از حد معمول بیشتر است — چون سرعت ارسال محدود و ثابت است، "
        "ارسال به همه ممکن است چند روز طول بکشد. ادامه می‌دهید؟"
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


async def get_soft_warning_threshold(db) -> int:
    """The current soft-warning threshold (default 30). Read-only convenience."""
    cfg = await get_config(db)
    return int(getattr(cfg, "soft_warning_threshold", None) or DEFAULT_SOFT_WARNING_THRESHOLD)


async def set_soft_warning_threshold(db, threshold: int) -> WarmupHelperConfig:
    """Set the soft-warning threshold (banner only — never blocks). Commits."""
    cfg = await get_config(db)
    cfg.soft_warning_threshold = max(1, int(threshold))
    await db.commit()
    return cfg


async def resolve_main_sender_instance_id(db) -> str | None:
    """The default 'main' sending account used to backfill legacy (senderless) V25 contacts:
    the default account → first warm peer → first active account."""
    from app.models.account import Account, AccountStatus
    accts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active).order_by(Account.created_at)
    )).scalars().all()
    if not accts:
        return None
    for a in accts:
        if getattr(a, "is_default", False):
            return a.instance_id
    for a in accts:
        if getattr(a, "is_warm_peer", False):
            return a.instance_id
    return accts[0].instance_id


# ── DB: contact CRUD (V28 — NO hard cap; per-sender scoping) ──────────────────
async def count_active_helpers(db) -> int:
    """Global active count (all senders). Kept for backward-compat."""
    return int((await db.execute(
        select(func.count()).select_from(WarmupHelper).where(WarmupHelper.is_active.is_(True))
    )).scalar() or 0)


async def count_helpers_for_sender(db, sender_instance_id: str, active_only: bool = True) -> int:
    """How many contacts belong to one sender (drives the soft-warning banner)."""
    q = select(func.count()).select_from(WarmupHelper).where(
        WarmupHelper.sender_instance_id == sender_instance_id)
    if active_only:
        q = q.where(WarmupHelper.is_active.is_(True))
    return int((await db.execute(q)).scalar() or 0)


async def list_helpers(db) -> list[WarmupHelper]:
    """All contacts across all senders (V25-compatible global list)."""
    return list((await db.execute(
        select(WarmupHelper).order_by(WarmupHelper.created_at)
    )).scalars().all())


async def list_helpers_for_sender(db, sender_instance_id: str) -> list[WarmupHelper]:
    """One sender's OWN contact list (lists never mix between senders)."""
    return list((await db.execute(
        select(WarmupHelper).where(WarmupHelper.sender_instance_id == sender_instance_id)
        .order_by(WarmupHelper.created_at)
    )).scalars().all())


async def add_helper(db, name: str, phone: str, is_active: bool = True,
                     sender_instance_id: str | None = None) -> WarmupHelper:
    """Add ONE known contact for a sender. V28 — NO hard count cap (pacing is the safety
    rail). `name` is MANDATORY (rejected with a Persian error if empty). Never auto-imports."""
    name = (name or "").strip()
    digits = wa_me_digits(phone)
    if not name:
        raise ValueError("نام مخاطب لازم است")
    if not digits:
        raise ValueError("شماره‌ی معتبر لازم است")
    helper = WarmupHelper(name=name, phone=digits, is_active=bool(is_active),
                          sender_instance_id=sender_instance_id)
    db.add(helper)
    await db.commit()
    await db.refresh(helper)
    return helper


async def update_helper(db, helper_id, *, name=None, phone=None, is_active=None,
                        sender_instance_id=None) -> WarmupHelper:
    """Edit a contact. V28 — no cap on (re)activation; `name` stays mandatory when provided."""
    helper = await db.get(WarmupHelper, helper_id)
    if helper is None:
        raise ValueError("مخاطب یافت نشد")
    if sender_instance_id is not None:
        helper.sender_instance_id = sender_instance_id
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


# ── V28 PART 5 — outreach dashboard aggregation ──────────────────────────────
# The sender role is INDEPENDENT of mesh warm-peer status (an account can be both, either, or
# neither). This note is surfaced per sender so the two roles are never conflated in the UI.
SENDER_ROLE_NOTE = "نقش «فرستنده‌ی ارتباط» مستقل از وضعیت «اکانت گرم مرجع» است؛ یک اکانت می‌تواند هر دو یا فقط یکی باشد."


def _iso(dt):
    return dt.isoformat() if dt else None


def assemble_outreach_dashboard(accounts, helpers, tasks,
                                threshold: int = DEFAULT_SOFT_WARNING_THRESHOLD) -> list[dict]:
    """PURE — build the per-sender dashboard from already-loaded rows. Each sender shows its
    contact count (+ soft-warning banner when large), a per-status task summary, and every
    contact with its task statuses per cold number. `accounts` need instance_id/name/is_warm_peer;
    `helpers` need id/name/phone/sender_instance_id/is_active; `tasks` need helper_id/
    cold_instance_id/status/asked_at/reminded_at/done_at."""
    tasks_by_helper: dict[str, list] = {}
    for t in tasks:
        tasks_by_helper.setdefault(str(t.helper_id), []).append(t)
    helpers_by_sender: dict = {}
    for h in helpers:
        helpers_by_sender.setdefault(h.sender_instance_id, []).append(h)

    out = []
    for a in accounts:
        own = helpers_by_sender.get(a.instance_id, [])
        active = sum(1 for h in own if h.is_active)
        status_summary = {STATUS_PENDING: 0, STATUS_ASKED: 0, STATUS_REMINDED: 0,
                          STATUS_DONE: 0, STATUS_SKIPPED: 0}
        contacts = []
        for h in own:
            htasks = tasks_by_helper.get(str(h.id), [])
            for t in htasks:
                if t.status in status_summary:
                    status_summary[t.status] += 1
            contacts.append({
                "id": str(h.id), "name": h.name, "phone": h.phone, "is_active": h.is_active,
                "tasks": [{
                    "cold_instance_id": t.cold_instance_id, "status": t.status,
                    "asked_at": _iso(getattr(t, "asked_at", None)),
                    "reminded_at": _iso(getattr(t, "reminded_at", None)),
                    "done_at": _iso(getattr(t, "done_at", None)),
                } for t in htasks],
            })
        out.append({
            "instance_id": a.instance_id, "name": a.name,
            "is_warm_peer": bool(getattr(a, "is_warm_peer", False)),
            "role_note": SENDER_ROLE_NOTE,
            "contact_count": active,
            "soft_warning": soft_warning_notice(active, threshold),
            "status_summary": status_summary,
            "contacts": contacts,
        })
    return out


async def build_outreach_dashboard(db) -> dict:
    """Load senders + contacts + tasks and assemble the per-sender dashboard."""
    from app.models.account import Account, AccountStatus
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active).order_by(Account.created_at)
    )).scalars().all()
    helpers = await list_helpers(db)
    tasks = (await db.execute(select(WarmupHelperTask))).scalars().all()
    threshold = await get_soft_warning_threshold(db)
    return {"threshold": threshold,
            "senders": assemble_outreach_dashboard(accounts, helpers, tasks, threshold)}
