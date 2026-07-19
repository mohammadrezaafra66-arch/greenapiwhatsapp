"""V30 PART 3 — «همکاری تیمی»-specific work-hours window: 09:00–19:00 Asia/Tehran.

A SEPARATE, narrower window than the mesh's own waking hours (DEFAULT_WARMUP_CONFIG's 09:00–21:00
used by `warmup_scheduler.in_active_hours`). No Team-Collaboration send — ask, reminder,
thank-you, or cold-reply — may occur outside 09:00–19:00 Tehran; the send defers to the next
valid window instead. This constant is intentionally independent so tightening the TC window never
touches the mesh's window (and vice-versa).

`in_team_hours` treats a naive datetime as Tehran-local (identical convention to
`warmup_scheduler.in_active_hours`), so the tick's Tehran-naive `now` is compared correctly.
"""
from __future__ import annotations
from datetime import datetime

from app.services.warmup_scheduler import to_tehran

# Team-Collaboration send window, Tehran-local. End is EXCLUSIVE (a send at 19:00 defers).
TEAM_HOURS_START = 9
TEAM_HOURS_END = 19


def in_team_hours(now: datetime, start: int = TEAM_HOURS_START, end: int = TEAM_HOURS_END) -> bool:
    """PURE. True only when `now` (naive → treated as Tehran) is within [start, end) Tehran-local.
    The single gate every «همکاری تیمی» send path consults, in addition to the mesh window."""
    local = to_tehran(now)
    return start <= local.hour < end
