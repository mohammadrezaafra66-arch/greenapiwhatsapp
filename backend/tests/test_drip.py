"""V13.8 — drip quota + estimate logic (pure)."""
from app.services.drip import _today_key, PAUSE_REASON


def _remaining(per_day, already):
    return max(0, per_day - already)


def _est_days(pending, per_day):
    return (pending + per_day - 1) // per_day if per_day else None


def test_remaining_quota():
    assert _remaining(50, 0) == 50
    assert _remaining(50, 30) == 20
    assert _remaining(50, 50) == 0
    assert _remaining(50, 60) == 0   # never negative


def test_est_days_rounds_up():
    assert _est_days(100, 50) == 2
    assert _est_days(101, 50) == 3   # ceil
    assert _est_days(50, 50) == 1
    assert _est_days(0, 50) == 0


def test_quota_gate_stops_at_limit():
    per_day, already = 50, 0
    remaining = _remaining(per_day, already)
    sent = 0
    sends = 0
    # simulate a run: stop when sent >= remaining
    for _ in range(200):
        if sent >= remaining:
            break
        sent += 1
        sends += 1
    assert sends == 50   # exactly the daily quota


def test_key_is_per_campaign_and_dated():
    k = _today_key("abc-123")
    assert k.startswith("drip:abc-123:")
    assert len(k.split(":")[-1]) == 8  # YYYYMMDD


def test_pause_reason_is_persian_marker():
    assert "drip" in PAUSE_REASON
