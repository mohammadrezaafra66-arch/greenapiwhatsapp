"""V30 PART 3 — «همکاری تیمی» work-hours window 09:00–19:00 Asia/Tehran.

Proves:
  • pure `in_team_hours`: [09:00, 19:00) Tehran, boundaries exact;
  • it is NARROWER than and independent of the mesh window (in_active_hours, 09:00–21:00) —
    20:00 is inside the mesh window but OUTSIDE the team window;
  • the live ask path (team-schedule tick) and cold-reply tick both DEFER outside the window.
"""
import random
from datetime import datetime
from unittest.mock import AsyncMock
import pytest

from app.services.warmup_team_hours import in_team_hours, TEAM_HOURS_START, TEAM_HOURS_END
from app.services.warmup_scheduler import in_active_hours
from app.services import warmup_team_schedule as ts
from app.services import warmup_cold_reply as ccr


def _t(h, m=0):
    return datetime(2026, 5, 4, h, m)   # naive → treated as Tehran


# ── pure window math ──────────────────────────────────────────────────────────
def test_in_team_hours_boundaries():
    assert TEAM_HOURS_START == 9 and TEAM_HOURS_END == 19
    assert in_team_hours(_t(9, 0)) is True       # start inclusive
    assert in_team_hours(_t(12, 30)) is True
    assert in_team_hours(_t(18, 59)) is True
    assert in_team_hours(_t(19, 0)) is False      # end exclusive
    assert in_team_hours(_t(19, 30)) is False
    assert in_team_hours(_t(8, 59)) is False
    assert in_team_hours(_t(3, 0)) is False


def test_team_window_narrower_than_and_independent_of_mesh():
    # 20:00 Tehran: inside the mesh waking window (09–21) but OUTSIDE the team window (09–19).
    assert in_active_hours(_t(20, 0)) is True
    assert in_team_hours(_t(20, 0)) is False
    # 08:00: outside both.
    assert in_active_hours(_t(8, 0)) is False
    assert in_team_hours(_t(8, 0)) is False


# ── the gate defers outside the window (no DB work needed — gate returns first) ──
@pytest.mark.asyncio
async def test_team_tick_defers_at_1930():
    db = AsyncMock()
    res = await ts.run_team_schedule_tick(db, now=_t(19, 30))
    assert res["acted"] == 0 and res.get("in_team_hours") is False
    db.execute.assert_not_awaited()   # deferred before any query


@pytest.mark.asyncio
async def test_team_tick_defers_at_0800_via_mesh_gate():
    db = AsyncMock()
    res = await ts.run_team_schedule_tick(db, now=_t(8, 0))
    assert res["acted"] == 0        # 08:00 is outside both windows → no send


@pytest.mark.asyncio
async def test_cold_reply_tick_defers_outside_team_window():
    db = AsyncMock()
    res = await ccr.run_cold_reply_tick(db, now=_t(19, 30), rng=random.Random(1))
    assert res["acted"] == 0 and res.get("in_team_hours") is False
    db.execute.assert_not_awaited()


class _EmptyResult:
    def scalars(self):
        class _S:
            def all(self_inner): return []
        return _S()


class _RecordingDB:
    def __init__(self): self.queried = False
    async def execute(self, q): self.queried = True; return _EmptyResult()
    async def commit(self): pass


@pytest.mark.asyncio
async def test_cold_reply_tick_runs_inside_team_window():
    # Inside the window it proceeds PAST the gate to query (no due rows → acted 0, but it queried).
    db = _RecordingDB()
    res = await ccr.run_cold_reply_tick(db, now=_t(11, 0), rng=random.Random(1))
    assert res["acted"] == 0 and res.get("in_team_hours") is None
    assert db.queried is True   # the team-hours gate did NOT short-circuit inside the window
