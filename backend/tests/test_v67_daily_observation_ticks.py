"""Session boundary and expected-tick tests."""
from __future__ import annotations
from datetime import datetime

from app.services.daily_observation.session_meta import SESSION_2_STARTED_AT_UTC
from app.services.daily_observation.ticks import (
    calendar_day_index,
    day_bounds_utc,
    format_tehran,
    observation_window_for_day,
)


def test_invalid_date_bounds_raises():
    try:
        day_bounds_utc("06-08-2026")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_day_bounds():
    s, e = day_bounds_utc("2026-08-05")
    assert s == datetime(2026, 8, 5)
    assert (e - s).days == 1


def test_date_before_session_not_applicable():
    w = observation_window_for_day("2026-08-04", now_utc=datetime(2026, 8, 10))
    assert w["not_applicable"] is True


def test_session2_day0_partial_from_start():
    w = observation_window_for_day(
        "2026-08-05",
        now_utc=datetime(2026, 8, 5, 23, 0, 0),
    )
    assert w["not_applicable"] is False
    assert w["window_start"] == SESSION_2_STARTED_AT_UTC
    # From 19:13:46 to 23:00 ≈ 3h46m → floor(/300) 
    assert w["expected_periodic_ticks"] >= 40
    assert w["partial_day"] is True


def test_full_utc_day_after_start():
    w = observation_window_for_day(
        "2026-08-06",
        now_utc=datetime(2026, 8, 10, 12, 0, 0),
    )
    assert w["not_applicable"] is False
    assert w["expected_periodic_ticks"] == 288  # 86400/300
    assert w["partial_day"] is False


def test_current_utc_day_partial_to_now():
    now = datetime(2026, 8, 7, 1, 0, 0)
    w = observation_window_for_day("2026-08-07", now_utc=now)
    assert w["window_end"] == now
    assert w["expected_periodic_ticks"] == int(3600 // 300)
    assert w["partial_day"] is True


def test_calendar_day_index_and_session1_excluded():
    assert calendar_day_index("2026-08-04") is None
    assert calendar_day_index("2026-08-05") == 0
    assert calendar_day_index("2026-08-06") == 1


def test_tehran_conversion():
    txt = format_tehran(SESSION_2_STARTED_AT_UTC)
    assert "زمان تهران" in txt
    assert "2026-08-05" in txt


def test_no_backdating_window_start():
    w = observation_window_for_day("2026-08-05", now_utc=datetime(2026, 8, 6))
    assert w["window_start"] >= SESSION_2_STARTED_AT_UTC
