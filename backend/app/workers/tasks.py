import asyncio
from app.workers.celery_app import celery_app
from app.services.campaign_runner import run_campaign

@celery_app.task(bind=True, name="tasks.run_campaign", max_retries=3)
def task_run_campaign(self, campaign_id: str):
    try:
        asyncio.run(run_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(bind=True, name="tasks.run_group_campaign", max_retries=3)
def task_run_group_campaign(self, campaign_id: str):
    try:
        from app.services.group_campaign_runner import run_group_campaign
        asyncio.run(run_group_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(name="tasks.clear_old_product_mentions")
def task_clear_old_product_mentions():
    async def _c():
        from app.database import AsyncSessionLocal
        from app.models.reporting import ProductMentionLog
        from sqlalchemy import delete
        from datetime import datetime, timedelta
        async with AsyncSessionLocal() as db:
            cutoff = datetime.utcnow() - timedelta(days=2)
            await db.execute(delete(ProductMentionLog).where(ProductMentionLog.mentioned_at < cutoff))
            await db.commit()
    asyncio.run(_c())

@celery_app.task(name="tasks.send_night_report")
def task_send_night_report():
    from app.services.night_report import send_night_report
    asyncio.run(send_night_report())

@celery_app.task(name="tasks.backfill_group_member_counts")
def task_backfill_group_member_counts():
    """Fill member_count/description for groups that have never been counted
    (member_count=0) or are stale (synced >7 days ago). Processed in batches of
    10 with a 2s pause between batches to avoid Green API rate limits."""
    async def _b():
        from app.database import AsyncSessionLocal
        from app.models.group import WhatsAppGroup
        from app.models.account import Account
        from app.services.green_api import GreenAPIClient
        from sqlalchemy import select, or_
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=7)
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(WhatsAppGroup).where(
                    WhatsAppGroup.green_group_id.isnot(None),
                    or_(
                        WhatsAppGroup.member_count == 0,
                        WhatsAppGroup.synced_at.is_(None),
                        WhatsAppGroup.synced_at < cutoff,
                    ),
                )
            )).scalars().all()

            acct_cache = {}
            updated = 0
            for i in range(0, len(rows), 10):
                batch = rows[i:i + 10]
                for grp in batch:
                    # getGroupData only works for real groups (@g.us), not broadcasts
                    if not grp.green_group_id or "@g.us" not in grp.green_group_id:
                        continue
                    if grp.account_id not in acct_cache:
                        acct_cache[grp.account_id] = await db.get(Account, grp.account_id)
                    account = acct_cache[grp.account_id]
                    if not account:
                        continue
                    try:
                        client = GreenAPIClient(account.instance_id, account.api_token)
                        data = await client.get_group_data(grp.green_group_id)
                        grp.member_count = len(data.get("participants", []))
                        desc = data.get("description")
                        if desc:
                            grp.description = desc
                        grp.synced_at = datetime.utcnow()
                        updated += 1
                    except Exception as e:
                        print(f"[Backfill] group {grp.green_group_id} error: {e}")
                await db.commit()
                await asyncio.sleep(2)  # pause between batches
            print(f"[Backfill] updated {updated}/{len(rows)} groups")
    asyncio.run(_b())

@celery_app.task(name="tasks.reset_daily_counters")
def task_reset_daily_counters():
    async def _r():
        from app.database import AsyncSessionLocal
        from app.models.account import Account
        from sqlalchemy import select
        from datetime import date
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account))
            for account in result.scalars().all():
                # Roll today's counts into yesterday before resetting
                account.received_yesterday = account.received_today
                account.sent_today = 0
                account.received_today = 0
                account.last_reset_date = date.today()
            await db.commit()
    asyncio.run(_r())

@celery_app.task(name="tasks.warmup_accounts")
def task_warmup_accounts():
    async def _w():
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.green_api import GreenAPIClient
        from app.services.warmup_service import post_daily_status
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account).where(Account.status == AccountStatus.active, Account.warmup_enabled == True))
            for account in result.scalars().all():
                client = GreenAPIClient(account.instance_id, account.api_token)
                await post_daily_status(client)
                account.days_active += 1
            await db.commit()
    asyncio.run(_w())

@celery_app.task(name="tasks.poll_accounts")
def task_poll_accounts():
    async def _p():
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.polling_service import poll_account_once
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Account).where(Account.status == AccountStatus.active, Account.polling_enabled == True)
            )
            accounts = result.scalars().all()
        for account in accounts:
            try:
                await poll_account_once(account)
            except Exception as e:
                print(f"[Polling] account {account.name} error: {e}")
    asyncio.run(_p())

@celery_app.task(name="tasks.sync_account_states")
def task_sync_account_states():
    async def _s():
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.green_api import GreenAPIClient
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account))
            for account in result.scalars().all():
                try:
                    client = GreenAPIClient(account.instance_id, account.api_token)
                    state = await client.get_state()
                    if state == "authorized":
                        account.status = AccountStatus.active
                    elif state == "blocked":
                        account.status = AccountStatus.banned
                    elif state == "notAuthorized":
                        account.status = AccountStatus.disconnected
                except Exception:
                    pass
            await db.commit()
    asyncio.run(_s())
