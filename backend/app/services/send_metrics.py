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


async def real_sent_today_by_account(db, now_utc: datetime | None = None) -> dict:
    """V35 PART 5 — the SAME cross-ledger 'sent today' as real_sent_today(), but computed PER
    ACCOUNT (keyed by instance_id) instead of only the global sum. The per-account dashboard chart
    ("ارسال امروز به تفکیک حساب") previously read only accounts.sent_today (the legacy campaign-only
    counter), so an account whose today's activity was Team-Collaboration / mesh / status showed 0.

    Returns {instance_id: {campaign, team_collaboration, mesh, status, total}}. Ledgers attribute a
    send to an account differently, so each is grouped by its own account key and mapped to the
    account's instance_id:
      • campaign     — CampaignContact.account_id  → instance_id (via the accounts table)
      • team-collab  — WarmupHelperLog.from_instance_id (the sender of the ask/reminder/thank-you)
      • mesh         — WarmupEventLog.enrollment_id → WarmupEnrollment.instance_id
      • status       — StatusSend.instance_id
    """
    from collections import defaultdict
    from app.models.campaign import CampaignContact
    from app.models.warmup_helpers import WarmupHelperLog
    from app.models.warmup_mesh import WarmupEventLog, WarmupEnrollment
    from app.models.status_send import StatusSend
    from app.models.account import Account

    start = tehran_today_start_utc(now_utc)
    out: dict[str, dict] = defaultdict(
        lambda: {"campaign": 0, "team_collaboration": 0, "mesh": 0, "status": 0, "total": 0})

    # account_id → instance_id, so campaign sends (keyed by account_id) can be attributed.
    id_to_instance = {aid: inst for aid, inst in
                      (await db.execute(select(Account.id, Account.instance_id))).all()}

    campaign_rows = (await db.execute(
        select(CampaignContact.account_id, func.count())
        .where(CampaignContact.sent_at.isnot(None), CampaignContact.sent_at >= start)
        .group_by(CampaignContact.account_id))).all()
    for account_id, cnt in campaign_rows:
        inst = id_to_instance.get(account_id)
        if inst:
            out[inst]["campaign"] += int(cnt or 0)

    team_rows = (await db.execute(
        select(WarmupHelperLog.from_instance_id, func.count())
        .where(WarmupHelperLog.message_sent.isnot(None), WarmupHelperLog.created_at >= start)
        .group_by(WarmupHelperLog.from_instance_id))).all()
    for inst, cnt in team_rows:
        if inst:
            out[inst]["team_collaboration"] += int(cnt or 0)

    mesh_rows = (await db.execute(
        select(WarmupEnrollment.instance_id, func.count())
        .select_from(WarmupEventLog)
        .join(WarmupEnrollment, WarmupEnrollment.id == WarmupEventLog.enrollment_id)
        .where(WarmupEventLog.event_type == "send", WarmupEventLog.created_at >= start)
        .group_by(WarmupEnrollment.instance_id))).all()
    for inst, cnt in mesh_rows:
        if inst:
            out[inst]["mesh"] += int(cnt or 0)

    status_rows = (await db.execute(
        select(StatusSend.instance_id, func.count())
        .where(StatusSend.created_at >= start)
        .group_by(StatusSend.instance_id))).all()
    for inst, cnt in status_rows:
        if inst:
            out[inst]["status"] += int(cnt or 0)

    for d in out.values():
        d["total"] = d["campaign"] + d["team_collaboration"] + d["mesh"] + d["status"]
    return dict(out)
