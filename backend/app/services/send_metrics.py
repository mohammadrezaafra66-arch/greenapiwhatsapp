"""V30 PART 8 — the REAL "today's sent count" for «داشبورد زنده».

ROOT CAUSE of the bug: the dashboard's "کل پیام‌های ارسالی امروز" was `sum(accounts.sent_today)`
— a per-account COUNTER incremented in only two code paths (campaign_runner + group_campaign_runner).
So any send that doesn't touch that counter was invisible: V29/V30 «همکاری تیمی» sends (their own
`warmup_helper_log` ledger), mesh sends (`warmup_event_log`), and status sends (`status_sends`).
On a Team-Collaboration-only day the dashboard therefore showed 0 despite dozens of real sends.

THE FIX: count today's ACTUAL outbound sends across ALL ledgers for the TEHRAN calendar day
(computed from real timestamps, not the UTC `CURRENT_DATE` default some tables use), so the number
is both complete AND correct across the UTC/Tehran day boundary.

Timestamps are stored naive-UTC (`datetime.utcnow()`); `tehran_today_start_utc` returns the
naive-UTC instant of 00:00 *today in Tehran*, and everything at/after it counts as "today".
"""
from __future__ import annotations
from datetime import datetime
import pytz
from sqlalchemy import select, func

TEHRAN = pytz.timezone("Asia/Tehran")


def tehran_today_start_utc(now_utc: datetime | None = None) -> datetime:
    """PURE. The naive-UTC instant of 00:00 *today in Tehran*, given a naive-UTC `now`.
    Everything at/after this instant belongs to the current Tehran calendar day."""
    now_utc = now_utc or datetime.utcnow()
    now_teh = pytz.utc.localize(now_utc).astimezone(TEHRAN)
    start_teh = TEHRAN.localize(datetime(now_teh.year, now_teh.month, now_teh.day))
    return start_teh.astimezone(pytz.utc).replace(tzinfo=None)


def count_since(timestamps, start_utc: datetime) -> int:
    """PURE. How many of `timestamps` (naive-UTC, None-tolerant) fall at/after `start_utc`."""
    return sum(1 for t in timestamps if t is not None and t >= start_utc)


async def real_sent_today(db, now_utc: datetime | None = None) -> dict:
    """Count today's (Tehran calendar day) REAL outbound sends across every ledger. Returns a
    breakdown + total so the dashboard reflects the true number, not just campaign-counter sends."""
    from app.models.campaign import CampaignContact
    from app.models.warmup_helpers import WarmupHelperLog
    from app.models.warmup_mesh import WarmupEventLog
    from app.models.status_send import StatusSend

    start = tehran_today_start_utc(now_utc)

    async def _count(stmt) -> int:
        return int((await db.execute(stmt)).scalar() or 0)

    campaign = await _count(
        select(func.count()).select_from(CampaignContact)
        .where(CampaignContact.sent_at.isnot(None), CampaignContact.sent_at >= start))
    # Team Collaboration OUTBOUND = log rows carrying a sent message (ask/reminder/thank-you/cold-reply).
    team = await _count(
        select(func.count()).select_from(WarmupHelperLog)
        .where(WarmupHelperLog.message_sent.isnot(None), WarmupHelperLog.created_at >= start))
    mesh = await _count(
        select(func.count()).select_from(WarmupEventLog)
        .where(WarmupEventLog.event_type == "send", WarmupEventLog.created_at >= start))
    status = await _count(
        select(func.count()).select_from(StatusSend)
        .where(StatusSend.created_at >= start))

    total = campaign + team + mesh + status
    return {
        "total": total,
        "campaign": campaign,
        "team_collaboration": team,
        "mesh": mesh,
        "status": status,
        "since_utc": start.isoformat(),
    }
