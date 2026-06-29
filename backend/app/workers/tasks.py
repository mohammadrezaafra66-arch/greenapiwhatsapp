import asyncio
from app.workers.celery_app import celery_app
from app.services.campaign_runner import run_campaign

@celery_app.task(bind=True, name="tasks.run_campaign", max_retries=3)
def task_run_campaign(self, campaign_id: str):
    try:
        asyncio.run(run_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

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
