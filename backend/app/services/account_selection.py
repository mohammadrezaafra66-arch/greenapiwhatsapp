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


def _key(value) -> str:
    """Normalise an account id for comparison.

    Ids reach us in two shapes: real UUID objects (the `selected_account_id` column, ORM rows)
    and plain strings (the V60 `selected_account_ids` JSONB array, and anything that came in
    over JSON). Comparing them directly would silently miss every match — the campaign would
    look like it had no eligible account and abort. Comparing on the string form makes the two
    interchangeable.
    """
    return str(value)


def selected_account_ids(campaign) -> set | None:
    """The set of account ids the user explicitly restricted the campaign to, or None when
    the user placed no restriction (legacy "any eligible account" behaviour).

    - explicit multi-selection (V60)   → that set, in ANY mode
    - parallel/all with no selection   → None  (unchanged legacy behaviour)
    - one account picked, not parallel → {that id}
    - nothing picked, not parallel     → None

    V60: `selected_account_ids` is the authority when present. It is honoured even with
    `parallel_accounts=True`, which is the whole point — "send concurrently from THESE three"
    used to be impossible to express, so parallel mode meant every active account.
    A selection can only ever narrow the sending set; it can never expand it.
    """
    multi = getattr(campaign, "selected_account_ids", None)
    if multi:
        return {_key(x) for x in multi}
    if getattr(campaign, "parallel_accounts", False):
        return None
    sel = getattr(campaign, "selected_account_id", None)
    return {sel} if sel else None


def filter_to_selection(eligible, selected_ids) -> list:
    """Intersect the eligible accounts with the explicit selection. When selected_ids is
    None (all/parallel), every eligible account is allowed."""
    if selected_ids is None:
        return list(eligible)
    wanted = {_key(s) for s in selected_ids}
    return [a for a in eligible if _key(getattr(a, "id", None)) in wanted]


def assert_sending_subset(accounts, selected_ids):
    """Hard invariant: `accounts` must be a SUBSET of the user's explicit selection.
    Returns accounts unchanged, or raises FanOutGuardError if anything escaped."""
    if selected_ids is None:
        return accounts
    wanted = {_key(s) for s in selected_ids}
    bad = [a for a in accounts if _key(getattr(a, "id", None)) not in wanted]
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
