"""V27 PART 7 — volume-spike guard for ALL sending instances.

A sudden day-over-day volume jump is flagged by WhatsApp independently of absolute daily
caps, and this risk applies to GRADUATED/established numbers too — not only numbers formally
inside the warm-up state machine. So for EVERY sending instance we compare today's planned
volume against its trailing 7-day average and, if it would be a large jump, cap today to a
smoother ramp (a long-quiet number can't suddenly blast a big campaign in one day).

A conservative floor means a quiet/new-but-warmed number sending a first small batch is NOT
flagged. Pure math is unit-testable; the async wrappers read trailing volume from
daily_send_logs. Fail-open — the guard never sends MORE than the existing hard cap.
"""
from __future__ import annotations
import logging
import math
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.models.reporting import DailySendLog
from app.services import governors

logger = logging.getLogger("afrakala.volume_guard")

# Today may be at most SPIKE_MULTIPLIER × the trailing average — but never less than
# MIN_DAILY_FLOOR (so a quiet number's first small batch isn't blocked) and never more than
# the account's own hard daily cap.
SPIKE_MULTIPLIER = 4.0
MIN_DAILY_FLOOR = 20
TRAILING_DAYS = 7


def spike_capped_volume(trailing_avg: float, hard_cap: int,
                        multiplier: float = SPIKE_MULTIPLIER,
                        floor: int = MIN_DAILY_FLOOR) -> int:
    """Max messages allowed today given the trailing daily average. Bounded below by `floor`
    and above by `hard_cap`."""
    spike_cap = max(int(floor), int(math.ceil(max(0.0, trailing_avg) * multiplier)))
    return max(0, min(int(hard_cap), spike_cap))


def is_spike(planned_today: int, trailing_avg: float,
             multiplier: float = SPIKE_MULTIPLIER, floor: int = MIN_DAILY_FLOOR) -> bool:
    """True if `planned_today` would be a flagged jump over the trailing average."""
    return int(planned_today) > max(int(floor), int(math.ceil(max(0.0, trailing_avg) * multiplier)))


async def trailing_daily_average(db, account_id, now: datetime | None = None,
                                 days: int = TRAILING_DAYS) -> float:
    """Average successful sends/day over the `days` full days BEFORE today (today excluded so
    today's own ramp doesn't inflate its baseline)."""
    now = now or datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    window_start = today_start - timedelta(days=days)
    total = (await db.execute(
        select(func.count()).select_from(DailySendLog).where(
            DailySendLog.account_id == account_id,
            DailySendLog.sent_at >= window_start,
            DailySendLog.sent_at < today_start,
            DailySendLog.status == "sent",
        )
    )).scalar() or 0
    return float(total) / float(days)


async def guarded_daily_cap(db, account, now: datetime | None = None) -> dict:
    """Today's effective cap for `account`, combining the existing hard cap with the spike
    guard. Returns {"hard_cap","trailing_avg","allowed","smoothed"}."""
    now = now or datetime.utcnow()
    hard = governors.effective_daily_cap(account, now)
    avg = await trailing_daily_average(db, account.id, now)
    allowed = spike_capped_volume(avg, hard)
    return {"hard_cap": hard, "trailing_avg": avg, "allowed": allowed,
            "smoothed": allowed < hard}


async def effective_daily_cap_guarded(db, account, now: datetime | None = None) -> int:
    """The single number the send loop should compare sent_today against."""
    res = await guarded_daily_cap(db, account, now)
    if res["smoothed"]:
        logger.info("volume-spike guard: instance=%s trailing_avg=%.1f hard_cap=%d -> allowed=%d",
                    getattr(account, "instance_id", "?"), res["trailing_avg"],
                    res["hard_cap"], res["allowed"])
    return res["allowed"]
