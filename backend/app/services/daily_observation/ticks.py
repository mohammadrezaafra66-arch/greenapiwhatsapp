"""Expected periodic tick calculation (UTC day / Session 2 aware)."""
from __future__ import annotations
from datetime import datetime, timedelta

from app.services.daily_observation.session_meta import (
    PERIODIC_TICK_INTERVAL_SECONDS,
    SESSION_2_STARTED_AT_UTC,
)


def day_bounds_utc(day_utc: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day_utc, "%Y-%m-%d")
    return start, start + timedelta(days=1)


def calendar_day_index(day_utc: str, session_start: datetime = SESSION_2_STARTED_AT_UTC) -> int | None:
    day0 = datetime(session_start.year, session_start.month, session_start.day)
    day_start, _ = day_bounds_utc(day_utc)
    if day_start < day0:
        return None
    return (day_start - day0).days


def observation_window_for_day(
    day_utc: str,
    *,
    now_utc: datetime | None = None,
    session_start: datetime = SESSION_2_STARTED_AT_UTC,
    interval_seconds: int = PERIODIC_TICK_INTERVAL_SECONDS,
) -> dict:
    """Return window used for expected-tick math.

    Current UTC day: window ends at now_utc (or utcnow).
    Past full day: window ends at day end.
    Days with no overlap after Session 2 start: not_applicable.
    """
    day_start, day_end = day_bounds_utc(day_utc)
    now = now_utc or datetime.utcnow()

    window_start = max(day_start, session_start)
    if window_start >= day_end:
        return {
            "not_applicable": True,
            "window_start": None,
            "window_end": None,
            "expected_periodic_ticks": 0,
            "partial_day": False,
            "interval_seconds": interval_seconds,
        }

    is_current_day = day_start.date() == now.date()
    if is_current_day:
        window_end = min(day_end, max(now, window_start))
        partial = True
    else:
        window_end = day_end
        partial = window_start > day_start

    if window_end <= window_start:
        expected = 0
    else:
        elapsed = (window_end - window_start).total_seconds()
        expected = int(elapsed // interval_seconds)

    return {
        "not_applicable": False,
        "window_start": window_start,
        "window_end": window_end,
        "expected_periodic_ticks": expected,
        "partial_day": partial,
        "interval_seconds": interval_seconds,
    }


def format_tehran(dt: datetime | None) -> str:
    if dt is None:
        return "نامشخص"
    try:
        from zoneinfo import ZoneInfo

        aware = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Tehran"))
        return aware.strftime("%Y-%m-%d %H:%M:%S") + " زمان تهران"
    except Exception:
        tehran = dt + timedelta(hours=3, minutes=30)
        return tehran.strftime("%Y-%m-%d %H:%M:%S") + " زمان تهران"
