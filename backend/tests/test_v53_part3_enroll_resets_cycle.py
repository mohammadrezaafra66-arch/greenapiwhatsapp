"""V53 PART 3 — re-enrolling a cold account must actually restart the 10-day cycle.

Live state that exposed this: three cold accounts sat at day 13 of a 10-day cycle with
`daily_step_budget` = 0, so «همکاری تیمی» sent nothing. The documented remedy was "re-enroll", but
`set_team_enrolled` stamped enrolled_at only when it was NULL. Pressing «enroll» on a row whose
enrolled_at was 2026-07-19 left the clock untouched → still day 13 → budget 0 → and
run_team_schedule_tick then set is_enabled=False again on its next pass. The button looked like it
worked and produced nothing.

Proves:
  • a brand-new enrollment stamps now / day 0 (unchanged behaviour);
  • re-enrolling an EXPIRED row resets enrolled_at to now and day_index to 0, so the budget is
    live again;
  • unenrolling preserves enrolled_at as history and does not reset the clock;
  • the reset genuinely changes the scheduler's answer (budget 0 -> 1).
"""
from datetime import datetime, timedelta

import pytest

from app.services import warmup_team_schedule as ts

NOW = datetime(2026, 8, 1, 12, 0)
OLD = datetime(2026, 7, 19, 13, 51)          # the real enrolled_at of the stuck accounts


class _Row:
    """Stand-in for an existing WarmupTeamEnrollment row."""

    def __init__(self, enrolled_at, is_enabled=True, day_index=10):
        self.cold_instance_id = "C1"
        self.is_enabled = is_enabled
        self.enrolled_at = enrolled_at
        self.day_index = day_index


class _DB:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_k):
        row = self.existing

        class _R:
            def scalar_one_or_none(_s):
                return row
        return _R()

    def add(self, o):
        self.added.append(o)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, o):
        pass


# ── the stuck state is real ──────────────────────────────────────────────────
def test_expired_cycle_has_no_budget():
    day = ts.team_day_index(OLD, NOW)
    assert day >= ts.TEAM_CYCLE_DAYS
    assert ts.daily_step_budget(day) == 0


# ── new enrollment: unchanged ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_new_enrollment_stamps_now_and_day_zero():
    db = _DB(existing=None)
    enr = await ts.set_team_enrolled(db, "C1", True, now=NOW)
    assert enr.is_enabled is True
    assert enr.enrolled_at == NOW
    assert enr.day_index == 0


# ── the fix ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_reenrolling_expired_row_resets_the_clock():
    row = _Row(enrolled_at=OLD, is_enabled=False, day_index=10)
    db = _DB(existing=row)
    enr = await ts.set_team_enrolled(db, "C1", True, now=NOW)
    assert enr.enrolled_at == NOW            # was OLD before the fix
    assert enr.day_index == 0
    assert enr.is_enabled is True


@pytest.mark.asyncio
async def test_reset_actually_restores_the_daily_budget():
    """The behavioural point: after re-enrolling, the scheduler has work to do again."""
    row = _Row(enrolled_at=OLD)
    assert ts.daily_step_budget(ts.team_day_index(row.enrolled_at, NOW)) == 0
    db = _DB(existing=row)
    enr = await ts.set_team_enrolled(db, "C1", True, now=NOW)
    day = ts.team_day_index(enr.enrolled_at, NOW)
    assert day == 0
    assert ts.daily_step_budget(day) == 1    # day 0 -> 1 conservative step


@pytest.mark.asyncio
async def test_reenrolling_a_midcycle_row_also_restarts_it():
    """Re-enrolling is an explicit operator decision; it restarts rather than resumes."""
    row = _Row(enrolled_at=NOW - timedelta(days=4), day_index=4)
    db = _DB(existing=row)
    enr = await ts.set_team_enrolled(db, "C1", True, now=NOW)
    assert enr.enrolled_at == NOW and enr.day_index == 0


# ── unenrolling keeps history ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_unenrolling_preserves_enrolled_at():
    row = _Row(enrolled_at=OLD, is_enabled=True, day_index=13)
    db = _DB(existing=row)
    enr = await ts.set_team_enrolled(db, "C1", False, now=NOW)
    assert enr.is_enabled is False
    assert enr.enrolled_at == OLD            # history preserved, clock untouched
    assert enr.day_index == 13
