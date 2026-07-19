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

from app.models.warmup_helpers import (
    WarmupHelper, WarmupHelperTask, WarmupHelperConfig, OutreachBrief, WarmupSenderConfig,
)
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
# V29 «همکاری تیمی» — the single reminder fires ~45–60 min after the ask if the contact hasn't
# acted. We fire at the top of that window (60 min) — one reminder per ask-STEP, never a second.
REMINDER_AFTER_HOURS = 1
REMINDER_WINDOW_MIN_MINUTES = 45
REMINDER_WINDOW_MAX_MINUTES = 60
REMINDER_AFTER_MINUTES = 60      # effective fire mark (within the 45–60 window)


def reminder_due(asked_at, now, after_minutes: int = REMINDER_AFTER_MINUTES) -> bool:
    """PURE. True when an ask-step is old enough (>= after_minutes) to warrant its ONE reminder.
    None asked_at → not due (never asked yet)."""
    if asked_at is None:
        return False
    return (now - asked_at).total_seconds() >= after_minutes * 60

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


# ── V29: per-sender enable flag (finer than the global toggle) ───────────────
async def get_sender_config(db, sender_instance_id: str) -> WarmupSenderConfig:
    """Fetch (or lazily create, default ON) one sender's «همکاری تیمی» config row."""
    cfg = (await db.execute(
        select(WarmupSenderConfig).where(
            WarmupSenderConfig.sender_instance_id == sender_instance_id).limit(1)
    )).scalar_one_or_none()
    if cfg is None:
        cfg = WarmupSenderConfig(sender_instance_id=sender_instance_id, is_enabled=True)
        db.add(cfg)
        await db.flush()
    return cfg


async def set_sender_enabled(db, sender_instance_id: str, enabled: bool) -> WarmupSenderConfig:
    """Flip ONE sender's «همکاری تیمی» toggle without touching the global master toggle. Commits."""
    cfg = await get_sender_config(db, sender_instance_id)
    cfg.is_enabled = bool(enabled)
    await db.commit()
    return cfg


async def is_sender_enabled(db, sender_instance_id: str | None) -> bool:
    """True when a sender may participate: a missing config row defaults to ON (opt-out model).
    A None sender (legacy senderless contact) is treated as enabled — the global toggle governs it."""
    if not sender_instance_id:
        return True
    cfg = (await db.execute(
        select(WarmupSenderConfig).where(
            WarmupSenderConfig.sender_instance_id == sender_instance_id).limit(1)
    )).scalar_one_or_none()
    return True if cfg is None else bool(cfg.is_enabled)


async def enabled_sender_ids(db) -> set[str]:
    """The set of sender instance_ids explicitly DISABLED, so callers can filter cheaply.
    Returns disabled ids (absence → enabled). Small table; one query."""
    rows = (await db.execute(
        select(WarmupSenderConfig.sender_instance_id, WarmupSenderConfig.is_enabled)
    )).all()
    return {sid for sid, en in rows if not en}


# ── V29: is_current brief (exactly one active per sender) ─────────────────────
async def set_current_brief(db, sender_instance_id: str, brief_text: str) -> OutreachBrief:
    """Append a new brief for a sender and mark it the ONLY current one (clears is_current on the
    sender's older rows). Append-only history is preserved; `is_current` names the active brief
    without relying on created_at ordering. Commits."""
    from sqlalchemy import update as _update
    await db.execute(
        _update(OutreachBrief)
        .where(OutreachBrief.sender_instance_id == sender_instance_id)
        .values(is_current=False)
    )
    brief = OutreachBrief(sender_instance_id=sender_instance_id,
                          brief_text=(brief_text or "").strip(), is_current=True)
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return brief


async def get_current_brief(db, sender_instance_id: str) -> OutreachBrief | None:
    """The sender's active brief (is_current=true). Falls back to the most-recent row if no row
    is flagged current yet (legacy pre-V29 briefs), so generation always has a seed if any exists."""
    cur = (await db.execute(
        select(OutreachBrief).where(
            OutreachBrief.sender_instance_id == sender_instance_id,
            OutreachBrief.is_current.is_(True),
        ).order_by(OutreachBrief.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if cur is not None:
        return cur
    return (await db.execute(
        select(OutreachBrief).where(OutreachBrief.sender_instance_id == sender_instance_id)
        .order_by(OutreachBrief.created_at.desc()).limit(1)
    )).scalar_one_or_none()


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


# V29 — the FULL name (first + last) is mandatory going forward. A single token (only a first
# name, no space) is rejected so «همکاری تیمی» always has a real person's full name to use.
FULL_NAME_REQUIRED_FA = "نام و نام خانوادگی (کامل) مخاطب لازم است."


def _normalize_full_name(name: str | None) -> str:
    """Collapse whitespace on a contact name. Returns '' when empty."""
    return " ".join((name or "").split())


def is_full_name(name: str | None) -> bool:
    """PURE. True only when `name` looks like a full name (>= 2 whitespace-separated tokens,
    each non-trivial). V29 requires first + last on every NEW/edited contact."""
    n = _normalize_full_name(name)
    if not n:
        return False
    parts = [p for p in n.split(" ") if len(p) >= 1]
    return len(parts) >= 2


async def add_helper(db, name: str, phone: str, is_active: bool = True,
                     sender_instance_id: str | None = None, *,
                     job_title: str | None = None, years_experience: int | None = None,
                     personal_benefit_note: str | None = None,
                     phone_secondary: str | None = None,
                     require_full_name: bool = False) -> WarmupHelper:
    """Add ONE known contact for a sender. V28 — NO hard count cap (pacing is the safety rail);
    `name` is MANDATORY (rejected if empty). V29 — the «همکاری تیمی» API passes
    `require_full_name=True` so NEW user-facing saves must carry a full name (first + last), plus
    the optional rich personnel profile the AI uses for personalized asks. Never auto-imports.

    (require_full_name defaults False so the V25/V28 service contract — a single-token name — is
    preserved for existing callers/tests; the full-name guardrail is enforced at the V29 boundary.)"""
    name = _normalize_full_name(name)
    digits = wa_me_digits(phone)
    if not name:
        raise ValueError("نام مخاطب لازم است")
    if require_full_name and not is_full_name(name):
        raise ValueError(FULL_NAME_REQUIRED_FA)
    if not digits:
        raise ValueError("شماره‌ی معتبر لازم است")
    sec = wa_me_digits(phone_secondary) or None
    yrs = _coerce_years(years_experience)
    helper = WarmupHelper(name=name, phone=digits, is_active=bool(is_active),
                          sender_instance_id=sender_instance_id,
                          job_title=(job_title or None) and job_title.strip() or None,
                          years_experience=yrs,
                          personal_benefit_note=(personal_benefit_note or None) and
                          personal_benefit_note.strip() or None,
                          phone_secondary=sec)
    db.add(helper)
    await db.commit()
    await db.refresh(helper)
    return helper


def _coerce_years(v) -> int | None:
    """Parse years_experience → non-negative int or None (accepts Persian digits). A negative
    input is rejected (returns None) rather than silently flipped by digit-stripping."""
    if v is None or v == "":
        return None
    if str(v).strip().startswith("-"):
        return None
    digits = wa_me_digits(str(v))
    if not digits:
        return None
    try:
        return int(digits)
    except (ValueError, TypeError):
        return None


_UNSET = object()


async def update_helper(db, helper_id, *, name=None, phone=None, is_active=None,
                        sender_instance_id=None, job_title=_UNSET, years_experience=_UNSET,
                        personal_benefit_note=_UNSET, phone_secondary=_UNSET,
                        require_full_name: bool = False) -> WarmupHelper:
    """Edit a contact. V28 — no cap on (re)activation; `name` stays mandatory when provided.
    V29 — the «همکاری تیمی» API passes `require_full_name=True` so an edited name must stay a
    full name; the rich-profile fields are individually patchable (pass a value to set, omit to
    leave unchanged, pass empty string to clear)."""
    helper = await db.get(WarmupHelper, helper_id)
    if helper is None:
        raise ValueError("مخاطب یافت نشد")
    if sender_instance_id is not None:
        helper.sender_instance_id = sender_instance_id
    if name is not None:
        name = _normalize_full_name(name)
        if not name:
            raise ValueError("نام فرد کمک‌کننده لازم است")
        if require_full_name and not is_full_name(name):
            raise ValueError(FULL_NAME_REQUIRED_FA)
        helper.name = name
    if phone is not None:
        digits = wa_me_digits(phone)
        if not digits:
            raise ValueError("شماره‌ی معتبر لازم است")
        helper.phone = digits
    if is_active is not None:
        helper.is_active = bool(is_active)
    if job_title is not _UNSET:
        helper.job_title = (job_title or None) and str(job_title).strip() or None
    if years_experience is not _UNSET:
        helper.years_experience = _coerce_years(years_experience)
    if personal_benefit_note is not _UNSET:
        helper.personal_benefit_note = (personal_benefit_note or None) and \
            str(personal_benefit_note).strip() or None
    if phone_secondary is not _UNSET:
        helper.phone_secondary = wa_me_digits(phone_secondary) or None
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


# ── V29: cold-account assignment (a contact's "path"; ceiling of 2) ──────────
# Each ask-message references AT MOST 2 cold accounts. Preferably ONE fixed cold account per
# contact (optionally reached from both the personal and «شماره کاری» work number). 2 is an
# explicit ceiling, NOT a default target. The (helper × cold) pairing is warmup_helper_task.
MAX_COLD_ACCOUNTS_PER_CONTACT = 2
COLD_CEILING_FA = (
    "هر مخاطب حداکثر می‌تواند به ۲ اکانت سرد اختصاص یابد. برای سادگی و طبیعی‌تربودن، "
    "ترجیحاً هر مخاطب را فقط به یک اکانت سرد اختصاص دهید."
)
COLD_ASSIGN_HINT_FA = (
    "برای سادگی و طبیعی‌تربودن، ترجیحاً هر مخاطب را فقط به یک اکانت سرد اختصاص دهید."
)


async def list_cold_accounts_for_helper(db, helper_id) -> list[str]:
    """The distinct cold-account instance_ids currently assigned to a contact (via its tasks)."""
    rows = (await db.execute(
        select(WarmupHelperTask.cold_instance_id).where(WarmupHelperTask.helper_id == helper_id)
    )).all()
    seen, out = set(), []
    for (cid,) in rows:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


async def count_cold_accounts_for_helper(db, helper_id) -> int:
    """How many DISTINCT cold accounts a contact is assigned to (the ceiling is 2)."""
    return len(await list_cold_accounts_for_helper(db, helper_id))


async def assign_cold_account(db, helper_id, cold_instance_id: str) -> WarmupHelperTask:
    """Assign a contact to a cold account (creates the pending (helper × cold) task). Idempotent
    for an existing pair; rejects with a Persian error once the contact already has 2 DISTINCT
    cold accounts. The DB-level UNIQUE also backstops accidental duplicates."""
    helper = await db.get(WarmupHelper, helper_id)
    if helper is None:
        raise ValueError("مخاطب یافت نشد")
    if not (cold_instance_id or "").strip():
        raise ValueError("اکانت سرد نامعتبر است")
    existing = await list_cold_accounts_for_helper(db, helper_id)
    if cold_instance_id in existing:
        # already assigned — return the existing task (idempotent), never a duplicate
        task = (await db.execute(
            select(WarmupHelperTask).where(
                WarmupHelperTask.helper_id == helper_id,
                WarmupHelperTask.cold_instance_id == cold_instance_id).limit(1)
        )).scalar_one_or_none()
        if task is not None:
            return task
    elif len(existing) >= MAX_COLD_ACCOUNTS_PER_CONTACT:
        raise ValueError(COLD_CEILING_FA)
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id=cold_instance_id,
                            status=STATUS_PENDING)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


# ── V30 PART 4 — completion-based escalation ─────────────────────────────────
# On a successful completion, GROW the relationship: assign up to this many NEW cold accounts
# (from the enrolled roster, never already-assigned/completed ones) as the contact's next round.
ESCALATION_BATCH = 2


async def escalate_after_completion(db, helper_id, *, batch: int = ESCALATION_BATCH) -> list[str]:
    """V30 PART 4. After a contact completes a task, assign up to `batch` NEW enrolled cold accounts
    (not yet assigned to this contact) as their next round. Returns the newly-assigned cold ids
    ([] when the roster is exhausted). Creates PENDING tasks only — the gated team tick decides WHEN
    the next ask actually goes out (per-sender 20-min spacing + 09–19 window + pacer all still apply).

    This deliberately BYPASSES the per-contact 2-ceiling of `assign_cold_account`: that ceiling caps
    how many cold accounts a SINGLE message references, whereas escalation legitimately grows the
    relationship ACROSS successful rounds. Already-completed cold accounts are never re-assigned
    (they are filtered out via the contact's existing assignments)."""
    from app.models.warmup_helpers import WarmupTeamEnrollment
    assigned = set(await list_cold_accounts_for_helper(db, helper_id))
    rows = (await db.execute(
        select(WarmupTeamEnrollment).where(WarmupTeamEnrollment.is_enabled.is_(True))
    )).scalars().all()
    pool = [r.cold_instance_id for r in rows if r.cold_instance_id and r.cold_instance_id not in assigned]
    new_ids = pool[:max(0, int(batch))]
    for cid in new_ids:
        db.add(WarmupHelperTask(helper_id=helper_id, cold_instance_id=cid, status=STATUS_PENDING))
    if new_ids:
        await db.flush()
    return new_ids


async def unassign_cold_account(db, helper_id, cold_instance_id: str) -> int:
    """Remove a contact↔cold-account assignment (delete its task rows). Returns rows removed."""
    tasks = (await db.execute(
        select(WarmupHelperTask).where(
            WarmupHelperTask.helper_id == helper_id,
            WarmupHelperTask.cold_instance_id == cold_instance_id)
    )).scalars().all()
    for t in tasks:
        await db.delete(t)
    if tasks:
        await db.commit()
    return len(tasks)


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
