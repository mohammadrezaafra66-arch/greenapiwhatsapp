"""V30 PART 8 — fix "today's sent count" on «داشبورد زنده».

Root cause: the stat was sum(accounts.sent_today) — a campaign-only counter that excluded «همکاری
تیمی», mesh, and status sends, so a Team-Collaboration-only day showed 0 despite real sends.

Proves:
  • `tehran_today_start_utc` computes the correct Tehran-calendar day boundary in UTC, so sends are
    bucketed to the right day across the UTC/Tehran boundary (Tehran = UTC+3:30);
  • `count_since` counts exactly the timestamps on/after that boundary (day-boundary seeding);
  • `real_sent_today` SUMS all ledgers — campaign + team_collaboration + mesh + status — so
    Team-Collaboration sends are now reflected in the total.
"""
from datetime import datetime
from unittest.mock import AsyncMock
import pytest

from app.services.send_metrics import tehran_today_start_utc, count_since, real_sent_today


# ── Tehran day boundary (Tehran = UTC + 3:30) ────────────────────────────────
def test_tehran_today_start_utc():
    # now = 2026-05-04 12:00 UTC → 15:30 Tehran on 05-04 → start of Tehran day = 05-03 20:30 UTC.
    start = tehran_today_start_utc(datetime(2026, 5, 4, 12, 0))
    assert start == datetime(2026, 5, 3, 20, 30)


def test_tehran_day_boundary_buckets_sends_correctly():
    now_utc = datetime(2026, 5, 4, 12, 0)       # 15:30 Tehran, 05-04
    start = tehran_today_start_utc(now_utc)       # 05-03 20:30 UTC
    sends = [
        datetime(2026, 5, 3, 20, 0),    # 23:30 Tehran 05-03 → YESTERDAY (before boundary)
        datetime(2026, 5, 3, 21, 0),    # 00:30 Tehran 05-04 → TODAY
        datetime(2026, 5, 4, 6, 0),     # 09:30 Tehran 05-04 → TODAY
        datetime(2026, 5, 4, 11, 59),   # 15:29 Tehran 05-04 → TODAY
        None,                            # never sent → ignored
    ]
    assert count_since(sends, start) == 3        # exactly the three on the Tehran 'today'


def test_count_since_empty():
    assert count_since([], tehran_today_start_utc(datetime(2026, 5, 4, 12, 0))) == 0


# ── real_sent_today sums ALL ledgers (the actual fix) ────────────────────────
class _CntRes:
    def __init__(self, n): self._n = n
    def scalar(self): return self._n


class _CntDB:
    """Returns a per-ledger count based on which table the COUNT query targets."""
    def __init__(self, campaign, team, mesh, status):
        self.map = {"campaign_contacts": campaign, "warmup_helper_log": team,
                    "warmup_event_log": mesh, "status_sends": status}
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        for table, n in self.map.items():
            if table in sql:
                return _CntRes(n)
        return _CntRes(0)


@pytest.mark.asyncio
async def test_real_sent_today_includes_team_collaboration():
    # The exact bug scenario: 0 campaign sends but 34 Team Collaboration sends today.
    db = _CntDB(campaign=0, team=34, mesh=0, status=0)
    out = await real_sent_today(db, now_utc=datetime(2026, 5, 4, 12, 0))
    assert out["total"] == 34                      # was 0 before the fix
    assert out["team_collaboration"] == 34
    assert out["campaign"] == 0


@pytest.mark.asyncio
async def test_real_sent_today_sums_every_ledger():
    db = _CntDB(campaign=3, team=34, mesh=2, status=1)
    out = await real_sent_today(db, now_utc=datetime(2026, 5, 4, 12, 0))
    assert out["total"] == 40
    assert out == {**out, "campaign": 3, "team_collaboration": 34, "mesh": 2, "status": 1}
