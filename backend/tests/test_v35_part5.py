"""V35 PART 5 — fix the per-account "ارسال امروز به تفکیک حساب" dashboard chart.

Two confirmed root causes, both fixed:
  1. /dashboard/stats' `detail` list included soft-deleted accounts, so a stale duplicate row
     (same display name, status=deleted) appeared on the chart's x-axis.
  2. The per-account breakdown used only accounts.sent_today (the legacy campaign-only counter),
     so an account whose today's activity came from Team Collaboration / mesh / status showed 0.
     V30 PART 8's cross-ledger fix was only applied to the TOTAL, not per account.

Proves: soft-deleted accounts are excluded from the chart data; a TC-only account shows the correct
non-zero per-account count; per-account counts sum every ledger; and V30 PART 8's top-line total
test is unaffected (it exercises real_sent_today, which is unchanged).
"""
from types import SimpleNamespace
from datetime import datetime
import uuid

import pytest

from app.api.v1 import dashboard as dash
from app.models.account import AccountStatus
from app.services.send_metrics import real_sent_today_by_account


def _acc(name, status=AccountStatus.active, instance_id="I", sent_today=0):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, phone="9891", status=status, instance_id=instance_id,
        sent_today=sent_today, received_today=0, computed_daily_limit=50,
        warmup_enabled=False, quota_exceeded_at=None)


# ── root cause #1 — soft-deleted excluded ─────────────────────────────────────
def test_soft_deleted_account_excluded_from_chart():
    live = _acc("افراکالا اصلی", AccountStatus.active, "I-live")
    dead = _acc("افراکالا اصلی", AccountStatus.deleted, "I-dead")     # the stale duplicate
    accounts = [live, dead]
    detail = [dash.account_detail_row(a, {}) for a in accounts if dash.account_in_chart(a)]
    names_statuses = [(d["name"], d["status"]) for d in detail]
    assert (live.name, AccountStatus.active) in names_statuses
    assert AccountStatus.deleted not in [d["status"] for d in detail]
    assert len(detail) == 1


def test_active_disconnected_banned_still_shown():
    accs = [_acc("a", AccountStatus.active), _acc("b", AccountStatus.disconnected),
            _acc("c", AccountStatus.banned)]
    kept = [a for a in accs if dash.account_in_chart(a)]
    assert len(kept) == 3       # only 'deleted' is filtered; others still monitored


# ── root cause #2 — per-account cross-ledger count ────────────────────────────
def test_detail_row_uses_cross_ledger_real_count():
    a = _acc("سارا", instance_id="INST-1", sent_today=0)     # 0 campaign sends
    per_account = {"INST-1": {"campaign": 0, "team_collaboration": 7, "mesh": 0,
                              "status": 0, "total": 7}}
    row = dash.account_detail_row(a, per_account)
    assert row["sent_today"] == 7             # chart reads this → now non-zero
    assert row["real_sent_today"] == 7
    assert row["campaign_sent_today"] == 0    # legacy counter preserved for reference


def test_detail_row_zero_when_no_activity():
    a = _acc("خالی", instance_id="INST-2")
    row = dash.account_detail_row(a, {})       # account absent from the per-account map
    assert row["sent_today"] == 0 and row["real_sent_today"] == 0


# ── real_sent_today_by_account attributes each ledger to the right account ─────
class _Rows:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _ByAccountDB:
    """Dispatches each grouped COUNT query to canned rows based on the target table in the SQL."""
    def __init__(self, accounts, campaign, team, mesh, status):
        self.accounts = accounts     # [(id, instance_id)]
        self.campaign = campaign     # [(account_id, count)]
        self.team = team             # [(from_instance_id, count)]
        self.mesh = mesh             # [(instance_id, count)]
        self.status = status         # [(instance_id, count)]

    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        # order matters: campaign_contacts/status_sends before the plain accounts select.
        if "campaign_contacts" in sql:
            return _Rows(self.campaign)
        if "warmup_helper_log" in sql:
            return _Rows(self.team)
        if "warmup_event_log" in sql or "warmup_enrollment" in sql:
            return _Rows(self.mesh)
        if "status_sends" in sql:
            return _Rows(self.status)
        if "accounts" in sql:
            return _Rows(self.accounts)
        return _Rows([])


@pytest.mark.asyncio
async def test_real_sent_today_by_account_team_only():
    aid = uuid.uuid4()
    db = _ByAccountDB(
        accounts=[(aid, "INST-1")],
        campaign=[],                       # no campaign sends today
        team=[("INST-1", 9)],              # 9 Team-Collaboration sends today
        mesh=[], status=[])
    out = await real_sent_today_by_account(db, now_utc=datetime(2026, 5, 4, 12, 0))
    assert out["INST-1"]["team_collaboration"] == 9
    assert out["INST-1"]["total"] == 9     # was invisible (0) before the fix


@pytest.mark.asyncio
async def test_real_sent_today_by_account_sums_all_ledgers():
    aid = uuid.uuid4()
    db = _ByAccountDB(
        accounts=[(aid, "INST-1")],
        campaign=[(aid, 3)],               # campaign keyed by account_id → mapped to INST-1
        team=[("INST-1", 4)],
        mesh=[("INST-1", 2)],
        status=[("INST-1", 1)])
    out = await real_sent_today_by_account(db, now_utc=datetime(2026, 5, 4, 12, 0))
    row = out["INST-1"]
    assert row["campaign"] == 3 and row["team_collaboration"] == 4
    assert row["mesh"] == 2 and row["status"] == 1
    assert row["total"] == 10


@pytest.mark.asyncio
async def test_real_sent_today_by_account_separates_accounts():
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    db = _ByAccountDB(
        accounts=[(a1, "INST-1"), (a2, "INST-2")],
        campaign=[(a1, 5)],
        team=[("INST-2", 8)],
        mesh=[], status=[])
    out = await real_sent_today_by_account(db, now_utc=datetime(2026, 5, 4, 12, 0))
    assert out["INST-1"]["total"] == 5
    assert out["INST-2"]["total"] == 8
