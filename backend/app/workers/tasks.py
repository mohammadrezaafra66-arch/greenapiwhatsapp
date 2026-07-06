import asyncio
from app.workers.celery_app import celery_app
from app.workers.async_helper import run_async
from app.services.campaign_runner import run_campaign

@celery_app.task(bind=True, name="tasks.run_campaign", max_retries=3)
def task_run_campaign(self, campaign_id: str, account_ids: list = None):
    try:
        if account_ids:
            from app.services.campaign_runner import run_campaign_parallel
            run_async(run_campaign_parallel(campaign_id, account_ids))
        else:
            run_async(run_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(bind=True, name="tasks.run_group_campaign", max_retries=3)
def task_run_group_campaign(self, campaign_id: str):
    try:
        from app.services.group_campaign_runner import run_group_campaign
        run_async(run_group_campaign(campaign_id))
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
    run_async(_c())

@celery_app.task(name="tasks.send_night_report")
def task_send_night_report():
    from app.services.night_report import send_night_report
    run_async(send_night_report())

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
            phone_cache = {}
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
                        # This account's own phone (fetched once), for admin detection.
                        if grp.account_id not in phone_cache:
                            try:
                                wa = await client.get_wa_settings()
                                phone_cache[grp.account_id] = str(wa.get("phone") or wa.get("wid") or "").split("@")[0]
                            except Exception:
                                phone_cache[grp.account_id] = ""
                        my_phone = phone_cache[grp.account_id]

                        data = await client.get_group_data(grp.green_group_id)
                        participants = data.get("participants", [])
                        grp.member_count = len(participants)
                        grp.participant_count = len(participants)
                        desc = data.get("description")
                        if desc:
                            grp.description = desc
                        if my_phone:
                            grp.is_admin = any(
                                str(p.get("id", "")).split("@")[0] == my_phone
                                and (p.get("isAdmin", False) or p.get("isSuperAdmin", False))
                                for p in participants
                            )
                        grp.synced_at = datetime.utcnow()
                        updated += 1
                    except Exception as e:
                        print(f"[Backfill] group {grp.green_group_id} error: {e}")
                await db.commit()
                await asyncio.sleep(2)  # pause between batches
            print(f"[Backfill] updated {updated}/{len(rows)} groups")
    run_async(_b())

@celery_app.task(name="tasks.extract_all_groups")
def task_extract_all_groups(account_id: str, instance_id: str, api_token: str, group_data: list):
    """Extract members from every given group and import them to contacts (no admin
    gate). group_data: list of [group_db_id, green_group_id, group_name]. Progress
    is tracked in Redis under extract_progress:{account_id}."""
    import redis
    from app.config import settings
    from app.services.green_api import GreenAPIClient
    from app.services.excel_service import normalize_phone
    from app.database import AsyncSessionLocal
    from app.models.contact import Contact
    from sqlalchemy import select as sa_select

    r = redis.from_url(settings.redis_url)
    progress_key = f"extract_progress:{account_id}"
    r.hset(progress_key, mapping={
        "status": "running", "processed": 0, "total": len(group_data),
        "added": 0, "skipped": 0, "current_group": "",
    })
    r.expire(progress_key, 3600)

    client = GreenAPIClient(instance_id, api_token)

    async def _run():
        total_added = 0
        total_skipped = 0
        for i, item in enumerate(group_data):
            green_group_id = item[1]
            group_name = item[2] or ""
            r.hset(progress_key, mapping={
                "processed": i, "current_group": group_name[:50],
                "added": total_added, "skipped": total_skipped,
            })
            try:
                resp = await client.get_group_data(green_group_id)
                participants = resp.get("participants", []) or []
                # Normalize + in-batch dedupe (A5: no per-row SELECT; bulk insert
                # with ON CONFLICT DO NOTHING relies on the unique index on phone).
                phones = []
                seen = set()
                for p in participants:
                    raw = str(p.get("id", "")).split("@")[0]
                    phone = normalize_phone(raw)
                    if not phone or phone in seen:
                        total_skipped += 1
                        continue
                    seen.add(phone)
                    phones.append(phone)

                if phones:
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    src = f"group:{group_name[:50]}"
                    gsrc = group_name[:500]
                    stmt = (
                        pg_insert(Contact)
                        .values([{"phone": ph, "source": src, "group_source": gsrc} for ph in phones])
                        .on_conflict_do_nothing(index_elements=["phone"])
                        .returning(Contact.id)
                    )
                    async with AsyncSessionLocal() as db:
                        res = await db.execute(stmt)
                        inserted = len(res.fetchall())
                        await db.commit()
                    total_added += inserted
                    total_skipped += len(phones) - inserted  # existing duplicates
                await asyncio.sleep(1)  # rate limit between groups
            except Exception as e:
                print(f"[BulkExtract] Group {group_name}: {e}")
                continue

        r.hset(progress_key, mapping={
            "status": "completed", "processed": len(group_data),
            "added": total_added, "skipped": total_skipped, "current_group": "",
        })
        r.expire(progress_key, 3600)

    run_async(_run())


@celery_app.task(name="tasks.recover_orphaned_campaigns")
def task_recover_orphaned_campaigns():
    """B1.4 — re-queue campaigns stuck in 'running' with pending contacts but no
    active run (no Redis lock held). run_campaign's lock prevents duplicates."""
    async def _o():
        from app.database import AsyncSessionLocal
        from app.models.campaign import Campaign, CampaignContact, CampaignStatus, MessageStatus
        from app.services import redis_rate_limiter
        from sqlalchemy import select, func
        async with AsyncSessionLocal() as db:
            running = (await db.execute(
                select(Campaign).where(Campaign.status == CampaignStatus.running)
            )).scalars().all()
        if not running:
            return
        try:
            r = await redis_rate_limiter.get_redis()
        except Exception:
            r = None
        for c in running:
            async with AsyncSessionLocal() as db:
                pending = (await db.execute(
                    select(func.count()).select_from(CampaignContact).where(
                        CampaignContact.campaign_id == c.id,
                        CampaignContact.status == MessageStatus.pending,
                    )
                )).scalar() or 0
            if not pending:
                continue
            held = False
            if r is not None:
                try:
                    held = bool(await r.exists(f"campaign_lock:{c.id}"))
                except Exception:
                    held = False
            if not held:
                task_run_campaign.delay(str(c.id))
                print(f"[Orphan] re-queued campaign {c.id} ({pending} pending, no active run)")
    run_async(_o())


@celery_app.task(name="tasks.reset_daily_counters")
def task_reset_daily_counters():
    async def _r():
        from app.database import AsyncSessionLocal
        from app.models.account import Account
        from sqlalchemy import select
        import pytz
        from datetime import datetime
        today_tehran = datetime.now(pytz.timezone("Asia/Tehran")).date()
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account))
            for account in result.scalars().all():
                # Roll today's counts into yesterday before resetting
                account.received_yesterday = account.received_today
                account.sent_today = 0
                account.received_today = 0
                account.last_reset_date = today_tehran
            await db.commit()
    run_async(_r())

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
    run_async(_w())

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
    run_async(_p())

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
    run_async(_s())
