"""V26 PART 1 — listener-role designation + mutual-exclusion guard.

CRITICAL rule (one account = one role): the group-monitoring "listener" account MUST be a
separate instance — never a campaign sender, a warm-up peer, or a cold warm-up number. This
module is the single guard that enforces that, in BOTH directions:

  • marking an account as a listener is blocked if it is already a warm peer, a legacy
    auto-warm account, or actively mesh-warming (enrolled and not yet GRADUATED);
  • marking an account as a warm peer / enrolling it in warm-up is blocked if it is a listener.

The decision helpers are PURE (they take precomputed flags) so they unit-test without a DB;
the async wrappers read the enrollment map and account row. All error strings are Persian.
"""
from __future__ import annotations
import logging
from sqlalchemy import select

logger = logging.getLogger("afrakala.listener")

# Persian error messages (UI-facing).
ERR_ALREADY_WARM_PEER = "این شماره به‌عنوان «همتای گرم‌سازی» تنظیم شده و نمی‌تواند حساب شنونده باشد. ابتدا نقش گرم‌سازی را بردارید."
ERR_ALREADY_WARMING = "این شماره در حال گرم‌سازی است و نمی‌تواند حساب شنونده باشد. یک شماره جدا و اختصاصی برای شنونده انتخاب کنید."
ERR_IS_LISTENER_WARM_PEER = "این شماره حساب شنونده است و نمی‌تواند همتای گرم‌سازی شود. نقش‌ها باید جدا بمانند."
ERR_IS_LISTENER_ENROLL = "این شماره حساب شنونده است و نمی‌تواند در گرم‌سازی ثبت شود. یک شماره دیگر انتخاب کنید."
ERR_IS_LISTENER_CAMPAIGN = "این شماره حساب شنونده است و فقط برای پایش گروه‌هاست؛ در کمپین‌ها استفاده نمی‌شود."


def can_mark_as_listener(*, is_warm_peer: bool, auto_warmup: bool,
                         is_actively_warming: bool) -> tuple[bool, str | None]:
    """Pure guard. Returns (ok, persian_error). Block if the account currently holds any
    conflicting role: warm peer, legacy auto-warm, or an active (non-graduated) enrollment."""
    if is_warm_peer:
        return False, ERR_ALREADY_WARM_PEER
    if auto_warmup or is_actively_warming:
        return False, ERR_ALREADY_WARMING
    return True, None


def can_mark_as_warm_peer(*, is_listener: bool) -> tuple[bool, str | None]:
    """Pure guard for the reverse direction — a listener can't become a warm peer."""
    if is_listener:
        return False, ERR_IS_LISTENER_WARM_PEER
    return True, None


def can_enroll_in_warmup(*, is_listener: bool) -> tuple[bool, str | None]:
    """Pure guard — a listener account must never be enrolled into warm-up."""
    if is_listener:
        return False, ERR_IS_LISTENER_ENROLL
    return True, None


def listener_campaign_excluded(account) -> bool:
    """True if `account` must be kept OUT of every campaign because it is a listener.
    Mirrors warmup_campaign_excluded so listeners never get pulled into a send."""
    return bool(getattr(account, "is_listener", False))


async def _is_actively_warming(db, instance_id: str) -> bool:
    """True if the instance has an active (is_enabled), non-GRADUATED warm-up enrollment.
    Fail-safe: on any read error returns False (never blocks on a transient DB glitch)."""
    try:
        from app.services.warmup_exclusion import active_warming_instance_ids
        return instance_id in await active_warming_instance_ids(db)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("active-warming check failed (fallback allow): %s", e)
        return False


async def set_listener(db, account, value: bool) -> tuple[bool, str | None]:
    """Set (or clear) an account's listener role, enforcing the mutual-exclusion guard.
    Returns (ok, persian_error). On success the caller commits."""
    if value:
        actively = await _is_actively_warming(db, account.instance_id)
        ok, err = can_mark_as_listener(
            is_warm_peer=bool(account.is_warm_peer),
            auto_warmup=bool(getattr(account, "auto_warmup", False)),
            is_actively_warming=actively,
        )
        if not ok:
            return False, err
    account.is_listener = bool(value)
    return True, None
