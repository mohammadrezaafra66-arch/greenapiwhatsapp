"""V60 STEP 0 — the campaign pre-flight brakes, shared by BOTH send paths.

Why this module exists. `_run_campaign_inner` (the sequential path) applies a chain of brakes
before it sends anything: the scheduled date window, the per-account send-hour window, the drip
quota, and the fail-closed account selection. `run_campaign_parallel` applied NONE of them — it
went straight from "here are the account ids" to `asyncio.gather(_send_chunk(...))`. So a campaign
with `parallel_accounts=true` could send outside 08:00–22:00 Tehran, ignore `drip_per_day`, ignore
`schedule_start`/`schedule_end`, and fan out past the user's account selection.

That is the opposite of what an operator expects: turning ON multi-account sending silently turned
OFF four brakes. This module holds the decisions ONCE so the two paths cannot drift again, and the
pure functions are unit-testable without a DB or Redis.

Nothing here relaxes an existing brake — every function either returns "go" or a reason to stop.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger("afrakala.campaign.preflight")

# The pause reason used when a campaign is parked outside every account's send window. Kept
# identical to campaign_runner.WINDOW_WAIT_REASON so the auto-resume test matches either path.
WINDOW_WAIT_REASON = "خارج از بازه مجاز ارسال این اکانت — ادامه خودکار در بازه بعدی"

# Decision verbs returned by check_schedule_window.
SCHEDULE_OK = "ok"
SCHEDULE_COMPLETE = "complete"      # past schedule_end → the campaign is genuinely finished
SCHEDULE_PARK = "park"              # before schedule_start → park and retry at that instant


def check_schedule_window(schedule_start, schedule_end, now: datetime) -> tuple[str, int]:
    """PURE. Decide what the scheduled date window says about running right now.

    Returns (decision, wait_seconds):
      • (SCHEDULE_COMPLETE, 0) — now is past `schedule_end`; the campaign is over.
      • (SCHEDULE_PARK, n)     — now is before `schedule_start`; retry in n seconds.
      • (SCHEDULE_OK, 0)       — inside the window (or no window configured).

    `now` must be UTC, matching how schedule_start/schedule_end are stored.
    """
    if schedule_end is not None and now > schedule_end:
        return SCHEDULE_COMPLETE, 0
    if schedule_start is not None and now < schedule_start:
        return SCHEDULE_PARK, max(1, int((schedule_start - now).total_seconds()))
    return SCHEDULE_OK, 0


def drip_remaining(drip_enabled: bool, drip_per_day, already_sent_today: int) -> int | None:
    """PURE. How many more messages this campaign may send today, or None when drip is off.

    None means "no campaign-level daily quota" — it must NOT be read as zero.
    """
    if not drip_enabled:
        return None
    return max(0, int(drip_per_day or 50) - int(already_sent_today or 0))


async def hour_window_wait_seconds(accounts) -> int:
    """How long until ANY of these accounts may send again. 0 when at least one can send now.

    Mirrors the sequential path: an account may send this hour when its per-account hour
    schedule (falling back to the global one) allows more than zero messages.
    """
    from app.services.rate_limiter import (
        get_max_per_hour_for_account, seconds_until_account_window,
    )
    caps = [await get_max_per_hour_for_account(str(a.id)) for a in accounts]
    if any(c > 0 for c in caps):
        return 0
    waits = [await seconds_until_account_window(str(a.id)) for a in accounts]
    positive = [w for w in waits if w > 0]
    return min(positive) if positive else 3600


async def new_contact_allowed(account, contact) -> bool:
    """Is this account allowed to message a contact it has never messaged before?

    V14 F23.6 caps accounts under 10 days old at 20 NEW contacts/day. The sequential path
    enforced this; the parallel path did not, which is exactly backwards — parallel sending is
    when a young account is most likely to burn through new contacts fast.
    """
    from app.services import governors
    if getattr(contact, "first_messaged_at", None) is not None:
        return True                                     # an existing contact is never capped
    return await governors.warmup_new_contact_allowed(
        str(account.id), getattr(account, "days_active", 0))
