"""
Night report: sends daily summary via WhatsApp to report subscribers.
Called by Celery beat at 23:00 Tehran time.
"""
import asyncio
from datetime import date
import pytz
from app.database import AsyncSessionLocal
from app.models.reporting import ReportSubscriber, DailySendLog
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from sqlalchemy import select, func, case

TEHRAN_TZ = pytz.timezone("Asia/Tehran")


async def send_night_report():
    today = date.today()

    async with AsyncSessionLocal() as db:
        # Get today's stats grouped by account
        stats_result = await db.execute(
            select(
                DailySendLog.account_name,
                func.count().label("total"),
                func.coalesce(func.sum(case((DailySendLog.status == "sent", 1), else_=0)), 0).label("sent"),
            )
            .where(DailySendLog.date == today)
            .group_by(DailySendLog.account_name)
        )
        stats = stats_result.all()

        if not stats:
            return  # Nothing to report

        # Build report message
        total_sent = sum(s.total for s in stats)
        report = "📊 گزارش روزانه افراکالا\n"
        report += f"📅 {today.strftime('%Y/%m/%d')}\n\n"
        report += f"✅ کل ارسال امروز: {total_sent} پیام\n\n"
        for s in stats:
            report += f"• {s.account_name or 'نامشخص'}: {s.total} پیام\n"

        # Get active account for sending
        acc_result = await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )
        account = acc_result.scalars().first()
        if not account:
            return

        client = GreenAPIClient(account.instance_id, account.api_token)

        # Get subscribers
        subs_result = await db.execute(
            select(ReportSubscriber).where(ReportSubscriber.is_active == True)
        )
        subscribers = subs_result.scalars().all()

        for sub in subscribers:
            try:
                await client.send_message(sub.phone, report)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[NightReport] Failed to send to {sub.phone}: {e}")
