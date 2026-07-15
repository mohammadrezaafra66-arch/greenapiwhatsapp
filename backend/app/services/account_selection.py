"""V18 PART 1 — fail-closed campaign account selection.

The rule: the set of sending instances is ALWAYS a subset of what the user explicitly
chose. Selecting one account must never expand to many. If the chosen account(s) are all
filtered out (cooldown / yellowCard / warming / not connected), the send ABORTS with a
clear Persian reason — it must NEVER silently fall back to sending from every account.

Pure and dependency-light so it unit-tests without a DB.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("afrakala.selection")

# Auto-pause reasons surfaced in the campaign progress panel.
NO_ACCOUNT_REASON = "هیچ اکانت فعالی متصل نیست — کمپین به‌طور خودکار متوقف شد"
SELECTED_ACCOUNT_UNAVAILABLE_REASON = (
    "اکانت انتخاب‌شده در دسترس نیست (استراحت/کارت زرد/عدم اتصال). "
    "کمپین ارسال نشد — یک اکانت سالم انتخاب کنید."
)


class FanOutGuardError(RuntimeError):
    """Raised if a resolved sending set escapes the user's explicit selection.

    A loud, last-line safety net: it should be impossible to reach, because
    resolve_sending_accounts only ever returns a subset — but if a future change breaks
    that, this stops a silent multi-account blast instead of letting it happen.
    """


def selected_account_ids(campaign) -> set | None:
    """The set of account UUIDs the user explicitly restricted the campaign to, or None
    when the user chose "all / parallel" (no single-account restriction).

    - parallel/all mode  → None  (multiple accounts allowed, by explicit choice)
    - one account picked  → {that id}
    - nothing picked, not parallel → None (legacy default: any eligible account)

    Note: picking one account yields a 1-element set; it can never expand to many.
    """
    if getattr(campaign, "parallel_accounts", False):
        return None
    sel = getattr(campaign, "selected_account_id", None)
    return {sel} if sel else None


def filter_to_selection(eligible, selected_ids) -> list:
    """Intersect the eligible accounts with the explicit selection. When selected_ids is
    None (all/parallel), every eligible account is allowed."""
    if selected_ids is None:
        return list(eligible)
    return [a for a in eligible if getattr(a, "id", None) in selected_ids]


def assert_sending_subset(accounts, selected_ids):
    """Hard invariant: `accounts` must be a SUBSET of the user's explicit selection.
    Returns accounts unchanged, or raises FanOutGuardError if anything escaped."""
    if selected_ids is None:
        return accounts
    bad = [a for a in accounts if getattr(a, "id", None) not in selected_ids]
    if bad:
        raise FanOutGuardError(
            "fan-out guard tripped: sending set includes non-selected accounts "
            f"{[str(getattr(a, 'id', None)) for a in bad]}"
        )
    return accounts


def resolve_sending_accounts(eligible, campaign) -> tuple[list, str | None]:
    """Decide which accounts a campaign may send from — FAIL-CLOSED.

    Returns (accounts, abort_reason):
      • accounts non-empty, abort_reason None  → send from exactly these (a subset of the
        user's explicit selection).
      • accounts empty, abort_reason set        → do NOT send; pause with this Persian reason.

    When a specific account is selected but not eligible, this returns the
    SELECTED_ACCOUNT_UNAVAILABLE_REASON — it never falls back to other accounts.
    """
    selected_ids = selected_account_ids(campaign)
    accounts = filter_to_selection(eligible, selected_ids)
    if selected_ids is not None:
        if not accounts:
            return [], SELECTED_ACCOUNT_UNAVAILABLE_REASON
        return assert_sending_subset(accounts, selected_ids), None
    # No explicit single selection (all/parallel or nothing picked).
    if not accounts:
        return [], NO_ACCOUNT_REASON
    return accounts, None
