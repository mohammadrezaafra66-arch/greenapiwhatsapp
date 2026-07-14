"""V14 PART C — message-control helpers (pure, testable)."""
from datetime import datetime, timedelta

# FEATURE 9 — WhatsApp/Green API only allow editing a message younger than 15 minutes.
EDIT_WINDOW_SECONDS = 15 * 60


def edit_window_ok(sent_at: datetime | None, now: datetime | None = None) -> bool:
    """True if `sent_at` is within the 15-minute edit window. Unknown sent_at → False
    (we cannot prove it's editable, so the server rejects to avoid a silent failure)."""
    if sent_at is None:
        return False
    now = now or datetime.utcnow()
    return (now - sent_at) <= timedelta(seconds=EDIT_WINDOW_SECONDS)


def edit_seconds_left(sent_at: datetime | None, now: datetime | None = None) -> int:
    """Seconds remaining in the edit window (0 if expired/unknown)."""
    if sent_at is None:
        return 0
    now = now or datetime.utcnow()
    left = EDIT_WINDOW_SECONDS - int((now - sent_at).total_seconds())
    return max(0, left)


# FEATURE 16 — the ONLY values setDisappearingChat accepts (seconds).
DISAPPEARING_VALUES = {0, 86400, 604800, 7776000}   # off · 24h · 7d · 90d


def valid_disappearing(value) -> bool:
    try:
        return int(value) in DISAPPEARING_VALUES
    except (TypeError, ValueError):
        return False
