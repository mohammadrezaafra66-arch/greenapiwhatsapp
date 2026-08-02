"""V60 PART B — allowed weekdays, and the hazard B-2 warned about.

The danger is not the feature, it is WHERE the check goes. Put it with the end-of-campaign
logic and a disallowed day would mark the campaign `completed` — permanently retiring a
campaign that still has contacts to reach, on a Friday. It belongs with the send-hour window:
a temporary condition that PARKS the campaign and retries.

Weekdays are Persian-indexed (شنبه=0 … جمعه=6) because that is the order the operator sees.
Python's weekday() is Monday=0, so the conversion is explicit — storing Python's numbering
would shift every choice by two days. And the day is computed on the TEHRAN calendar: Friday
there begins 3.5 hours before Friday in UTC.
"""
import inspect
from datetime import datetime

import pytest

from app.api.v1.campaigns import _clean_weekdays
from app.services import campaign_preflight as pf
from app.services import campaign_runner as cr

# 2026-08-01 is a Saturday → Persian شنبه = 0
SAT = datetime(2026, 8, 1, 12, 0)
SUN = datetime(2026, 8, 2, 12, 0)
MON = datetime(2026, 8, 3, 12, 0)
THU = datetime(2026, 8, 6, 12, 0)
FRI = datetime(2026, 8, 7, 12, 0)


# ── Persian weekday mapping ─────────────────────────────────────────────────
def test_persian_weekday_starts_on_saturday():
    assert pf.persian_weekday(SAT) == 0      # شنبه
    assert pf.persian_weekday(SUN) == 1      # یکشنبه
    assert pf.persian_weekday(MON) == 2      # دوشنبه
    assert pf.persian_weekday(THU) == 5      # پنجشنبه
    assert pf.persian_weekday(FRI) == 6      # جمعه


def test_the_seven_labels_line_up_with_the_indices():
    assert pf.WEEKDAY_FA[0] == "شنبه"
    assert pf.WEEKDAY_FA[6] == "جمعه"
    assert len(pf.WEEKDAY_FA) == 7


# ── is_send_day ─────────────────────────────────────────────────────────────
def test_no_restriction_allows_every_day():
    for day in (SAT, SUN, MON, THU, FRI):
        assert pf.is_send_day(None, day) is True
        assert pf.is_send_day([], day) is True


def test_saturday_to_wednesday_excludes_thursday_and_friday():
    allowed = [0, 1, 2, 3, 4]        # شنبه … چهارشنبه
    assert pf.is_send_day(allowed, SAT) is True
    assert pf.is_send_day(allowed, MON) is True
    assert pf.is_send_day(allowed, THU) is False
    assert pf.is_send_day(allowed, FRI) is False


def test_unreadable_config_does_not_silently_block_sending():
    """A corrupt value must fail OPEN — parking a campaign forever is worse than sending."""
    assert pf.is_send_day(["x", None], SAT) is True


# ── seconds_until_next_send_day ─────────────────────────────────────────────
def test_no_wait_when_today_is_allowed():
    assert pf.seconds_until_next_send_day([0, 1, 2], SAT) == 0


def test_friday_waits_until_saturday_midnight():
    # Friday 12:00 → Saturday 00:00 is 12 hours
    wait = pf.seconds_until_next_send_day([0, 1, 2, 3, 4], FRI)
    assert wait == pytest.approx(12 * 3600, abs=2)


def test_thursday_with_only_saturday_allowed_waits_two_nights():
    wait = pf.seconds_until_next_send_day([0], THU)
    assert wait == pytest.approx(36 * 3600, abs=2)   # Thu 12:00 → Sat 00:00


def test_wait_is_never_zero_when_today_is_disallowed():
    """A zero countdown would busy-loop the broker all day."""
    assert pf.seconds_until_next_send_day([0], FRI) >= 1


def test_a_config_allowing_nothing_retries_tomorrow_instead_of_spinning():
    assert pf.seconds_until_next_send_day([99], FRI) == 86400


# ── Tehran calendar ─────────────────────────────────────────────────────────
def test_tehran_now_is_ahead_of_utc():
    utc = datetime(2026, 8, 1, 12, 0)
    teh = pf.tehran_now(utc)
    assert (teh - utc).total_seconds() == pytest.approx(3.5 * 3600, abs=60)


def test_the_day_boundary_follows_tehran_not_utc():
    """21:00 UTC Thursday is already Friday 00:30 in Tehran — the two calendars disagree,
    and the operator means the Tehran one."""
    utc_thursday_late = datetime(2026, 8, 6, 21, 0)
    teh = pf.tehran_now(utc_thursday_late)
    assert pf.persian_weekday(teh) == 6                     # جمعه in Tehran
    assert pf.persian_weekday(utc_thursday_late) == 5       # still پنجشنبه in UTC
    assert pf.is_send_day([0, 1, 2, 3, 4], teh) is False


# ── input sanitising ────────────────────────────────────────────────────────
def test_clean_weekdays_sorts_and_dedupes():
    assert _clean_weekdays([4, 0, 4, 2]) == [0, 2, 4]


def test_clean_weekdays_drops_out_of_range_and_garbage():
    assert _clean_weekdays([0, 9, -1, "x", None, 3]) == [0, 3]


def test_clean_weekdays_empty_means_every_day_not_no_day():
    """A user who clears every toggle means "no restriction". Read literally, an empty list
    would park the campaign forever."""
    assert _clean_weekdays([]) is None
    assert _clean_weekdays(None) is None
    assert _clean_weekdays(["nonsense"]) is None


def test_all_seven_selected_is_stored_as_no_restriction():
    assert _clean_weekdays([0, 1, 2, 3, 4, 5, 6]) is None


# ── the B-2 hazard: park, never complete ────────────────────────────────────
def test_both_paths_park_on_a_disallowed_day_and_never_complete():
    """The B-2 hazard itself: a Friday must pause the campaign, never retire it."""
    for fn in (cr._run_campaign_inner, cr._run_campaign_parallel_inner):
        src = inspect.getsource(fn)
        brake = _brake_at(src)
        window = src[brake - 200:brake + 600]
        assert "CampaignStatus.paused" in window
        assert "CampaignStatus.completed" not in window


def _brake_at(src: str) -> int:
    """Index of the line that SETS the weekday pause, not the auto-resume comparison above it."""
    at = src.index("pause_reason = ")
    while "DAY_NOT_ALLOWED_REASON" not in src[at:at + 60]:
        at = src.index("pause_reason = ", at + 1)
    return at


def test_the_weekday_check_runs_after_the_schedule_decision():
    """B-2 ordering. It must sit AFTER the schedule window (so passing schedule_end still
    completes the campaign) and BEFORE the hour window (so both temporary conditions park it
    the same way)."""
    for fn in (cr._run_campaign_inner, cr._run_campaign_parallel_inner):
        src = inspect.getsource(fn)
        brake = _brake_at(src)
        assert src.index("schedule") < brake
        assert brake < src.index("pause_reason = WINDOW_WAIT_REASON")


def test_both_paths_reschedule_for_the_next_allowed_day():
    for fn in (cr._run_campaign_inner, cr._run_campaign_parallel_inner):
        src = inspect.getsource(fn)
        brake = _brake_at(src)
        assert "seconds_until_next_send_day" in src[brake:brake + 700]


def test_auto_resume_recognises_a_weekday_pause():
    """Without this the parked campaign would wake up and immediately return, because the
    resume check only knew about the window and schedule reasons."""
    for fn in (cr._run_campaign_inner, cr._run_campaign_parallel_inner):
        src = inspect.getsource(fn)
        resume_at = src.index("Auto-resume") if "Auto-resume" in src else 0
        assert "DAY_NOT_ALLOWED_REASON" in src[resume_at:resume_at + 800]


def test_weekday_uses_the_tehran_clock_in_both_paths():
    for fn in (cr._run_campaign_inner, cr._run_campaign_parallel_inner):
        src = inspect.getsource(fn)
        at = src.index("is_send_day")
        assert "tehran_now" in src[at:at + 200]
