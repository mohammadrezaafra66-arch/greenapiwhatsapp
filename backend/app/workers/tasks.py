import asyncio
from app.workers.celery_app import celery_app
from app.services.campaign_runner import run_campaign


@celery_app.task(bind=True, name="tasks.run_campaign", max_retries=3)
def task_run_campaign(self, campaign_id: str):
    """Run a campaign in the background."""
    try:
        asyncio.run(run_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.reset_daily_counters")
def task_reset_daily_counters():
    """Reset sent_today counters at midnight. Schedule this with celery beat."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.models.account import Account
    from sqlalchemy import update
    from datetime import date

    async def _reset():
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Account).values(
                    sent_today=0,
                    last_reset_date=date.today()
                )
            )
            await db.commit()

    asyncio.run(_reset())


@celery_app.task(name="tasks.update_daily_limits")
def task_update_daily_limits():
    """Recalculate daily limits based on formula. Run every hour."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.models.account import Account
    from sqlalchemy import select

    async def _update():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account))
            accounts = result.scalars().all()
            for account in accounts:
                account.daily_limit = account.computed_daily_limit
            await db.commit()

    asyncio.run(_update())
