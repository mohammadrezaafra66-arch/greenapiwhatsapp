"""Utilities for Shamsi (Jalali) date conversion."""
import jdatetime
from datetime import datetime
import pytz

TEHRAN_TZ = pytz.timezone("Asia/Tehran")


def to_shamsi(dt: datetime | None) -> str | None:
    """Convert a (naive UTC) datetime to a Shamsi display string in Tehran time."""
    if not dt:
        return None
    try:
        tehran_dt = dt.replace(tzinfo=pytz.utc).astimezone(TEHRAN_TZ)
        jdt = jdatetime.datetime.fromgregorian(datetime=tehran_dt)
        return jdt.strftime("%Y/%m/%d %H:%M")
    except Exception:
        return None


def from_shamsi(shamsi_str: str) -> datetime | None:
    """Parse a Shamsi datetime string ('YYYY/MM/DD HH:MM', Tehran) to naive UTC."""
    if not shamsi_str:
        return None
    try:
        jdt = jdatetime.datetime.strptime(shamsi_str.strip(), "%Y/%m/%d %H:%M")
        gregorian = jdt.togregorian()
        tehran_dt = TEHRAN_TZ.localize(gregorian)
        return tehran_dt.astimezone(pytz.utc).replace(tzinfo=None)
    except Exception:
        return None
