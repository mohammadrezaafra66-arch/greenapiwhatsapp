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


# V26 PART 4 — transcribe a monitored-group voice note (Whisper, Persian), then run the
# SAME keyword detection / auto-reply on the transcript. rate_limit caps concurrency so a
# busy group can't hammer the OpenAI API; exponential backoff on retryable errors.
@celery_app.task(bind=True, name="tasks.transcribe_group_voice", max_retries=4,
                 rate_limit="20/m")
def task_transcribe_group_voice(self, gm_id: str):
    try:
        from app.services.group_voice import process_voice_message
        run_async(process_voice_message(gm_id))
    except Exception as exc:
        # 30s, 60s, 120s, 240s backoff (idempotent: a 'done' row is skipped on retry).
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

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

@celery_app.task(name="tasks.recall_campaign")
def task_recall_campaign(campaign_id: str):
    """V14 F10 — delete every message a campaign sent (10/sec), in the background."""
    from app.services.recall import recall_campaign
    run_async(recall_campaign(campaign_id))


@celery_app.task(name="tasks.safe_add_participants")
def task_safe_add_participants(group_db_id: str, phones: list):
    """V14 F22 — ban-guarded group-member add (checkWhatsapp + caps + 1024 guard)."""
    from app.services.group_add import safe_add_participants
    run_async(safe_add_participants(group_db_id, list(phones)))


@celery_app.task(name="tasks.apply_profile_picture_all")
def task_apply_profile_picture_all(image_path: str):
    """V14 F17 — set the same profile picture on every active account, 10s apart
    (0.1/sec limit). Publishes {done,total,finished} to Redis for the progress UI."""
    import os, json
    async def _run():
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.green_api import GreenAPIClient
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        try:
            with open(image_path, "rb") as fh:
                data = fh.read()
            async with AsyncSessionLocal() as db:
                accounts = (await db.execute(
                    select(Account).where(Account.status == AccountStatus.active)
                )).scalars().all()
                total = len(accounts)
                done = 0
                await r.set("pfp_apply_progress", json.dumps({"done": 0, "total": total, "finished": False}), ex=3600)
                for i, acc in enumerate(accounts):
                    try:
                        res = await GreenAPIClient(acc.instance_id, acc.api_token).set_profile_picture_upload(data)
                        url = res.get("urlAvatar") if isinstance(res, dict) else None
                        if url:
                            acc.profile_picture_url = url
                            await db.commit()
                        done += 1
                    except Exception as e:
                        print(f"[pfp-all] account {acc.instance_id} failed: {e}")
                    await r.set("pfp_apply_progress", json.dumps({"done": done, "total": total, "finished": False}), ex=3600)
                    if i < total - 1:
                        await asyncio.sleep(10)   # 0.1/sec — one call per 10 seconds
                await r.set("pfp_apply_progress", json.dumps({"done": done, "total": total, "finished": True}), ex=3600)
        finally:
            try:
                os.remove(image_path)
            except Exception:
                pass
    run_async(_run())


@celery_app.task(name="tasks.detect_yellow_cards")
def task_detect_yellow_cards():
    """V14 F23.1 — poll getStateInstance per active account every 2 min (webhooks can be
    missed when the tunnel dies). A yellowCard triggers the automatic incident response."""
    async def _run():
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.green_api import GreenAPIClient
        from app.services import governors
        from app.services.incident_handler import handle_yellow_card
        async with AsyncSessionLocal() as db:
            accounts = (await db.execute(select(Account).where(Account.status == AccountStatus.active))).scalars().all()
            for acc in accounts:
                if governors.in_cooldown(acc):
                    continue   # already handled/resting
                try:
                    state = await GreenAPIClient(acc.instance_id, acc.api_token).get_state()
                except Exception:
                    continue
                if state == "yellowCard":
                    await handle_yellow_card(acc, "poll", db)
    run_async(_run())


@celery_app.task(name="tasks.poll_instance_states")
def task_poll_instance_states():
    """V27 PART 4 — poll getStateInstance for every active instance on a ~60s cadence
    (staggered to avoid a thundering herd), refresh the live-state cache the pre-send gate
    reads, and immediately quarantine any instance reporting a danger state. get_state is a
    plain GET — this is NOT Green API message-polling (webhook-only receipt stays intact)."""
    async def _run():
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.green_api import GreenAPIClient
        from app.services.state_monitor import apply_state
        async with AsyncSessionLocal() as db:
            accounts = (await db.execute(
                select(Account).where(Account.status == AccountStatus.active))).scalars().all()
            total = len(accounts)
            for i, acc in enumerate(accounts):
                try:
                    state = await GreenAPIClient(acc.instance_id, acc.api_token).get_state()
                except Exception:
                    continue
                try:
                    await apply_state(db, acc, state, "poll")
                except Exception:
                    pass
                if i < total - 1:
                    await asyncio.sleep(0.5)   # stagger across the ~60s window
            await db.commit()
    run_async(_run())


@celery_app.task(name="tasks.quality_score_monitor")
def task_quality_score_monitor():
    """V27 PART 8 — hourly per-instance quality score (reply-rate + failure-rate). A low score
    auto-throttles that instance's outbound campaign sending and records a Persian dashboard
    warning. Applies to every active sending instance, not only warm-up enrollments."""
    async def _run():
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.quality_score import evaluate_and_act
        async with AsyncSessionLocal() as db:
            accounts = (await db.execute(
                select(Account).where(Account.status == AccountStatus.active))).scalars().all()
            acted = False
            for acc in accounts:
                try:
                    res = await evaluate_and_act(db, acc)
                    acted = acted or (res.get("acted") == "throttled")
                except Exception:
                    continue
            if acted:
                await db.commit()
    run_async(_run())


@celery_app.task(name="tasks.sync_call_logs")
def task_sync_call_logs():
    """V14 F24 — pull the call journals every 30 min (complements live webhooks)."""
    async def _run():
        from datetime import datetime
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.models.incident import CallLog
        from app.services.green_api import GreenAPIClient
        async with AsyncSessionLocal() as db:
            accounts = (await db.execute(select(Account).where(Account.status == AccountStatus.active))).scalars().all()
            for acc in accounts:
                client = GreenAPIClient(acc.instance_id, acc.api_token)
                for direction, fetch in (("incoming", client.last_incoming_calls), ("outgoing", client.last_outgoing_calls)):
                    try:
                        calls = await fetch(60)
                    except Exception:
                        continue
                    for c in (calls or []):
                        ts = c.get("timestamp") or c.get("time") or 0
                        try:
                            called_at = datetime.fromtimestamp(int(ts)) if ts else None
                        except Exception:
                            called_at = None
                        phone = str(c.get("from") or c.get("chatId") or c.get("sender") or "").split("@")[0]
                        # best-effort dedup by (phone, called_at, direction)
                        exists = (await db.execute(select(CallLog).where(
                            CallLog.from_phone == phone, CallLog.called_at == called_at,
                            CallLog.direction == direction,
                        ).limit(1))).scalar_one_or_none()
                        if exists:
                            continue
                        db.add(CallLog(account_id=acc.id, direction=direction, from_phone=phone,
                                       status=c.get("status"), called_at=called_at))
                    await db.commit()
    run_async(_run())


@celery_app.task(name="tasks.reply_rate_monitor")
def task_reply_rate_monitor():
    """V14 F23.6 — 7-day reply rate per account; <10% → auto-throttle 0.5 (warning)."""
    async def _run():
        from datetime import datetime, timedelta
        from sqlalchemy import select, func
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.models.campaign import CampaignContact
        from app.services import governors
        from app.services.incident_handler import apply_warning_throttle
        cutoff = datetime.utcnow() - timedelta(days=7)
        async with AsyncSessionLocal() as db:
            accounts = (await db.execute(select(Account).where(Account.status == AccountStatus.active))).scalars().all()
            for acc in accounts:
                total = (await db.execute(select(func.count()).select_from(CampaignContact).where(
                    CampaignContact.account_id == acc.id, CampaignContact.sent_at >= cutoff))).scalar() or 0
                if total < 20:
                    continue   # not enough volume to judge
                replied = (await db.execute(select(func.count()).select_from(CampaignContact).where(
                    CampaignContact.account_id == acc.id, CampaignContact.sent_at >= cutoff,
                    CampaignContact.replied.is_(True)))).scalar() or 0
                rate = replied / total
                if rate < 0.10 and not governors.is_throttled(acc):
                    await apply_warning_throttle(acc, "lowReplyRate", "poll", db, factor=0.5, days=7)
    run_async(_run())


@celery_app.task(name="tasks.process_warmup_accounts")
def task_process_warmup_accounts():
    """V15 Item 26 — daily managed warm-up: advance each auto-warming account and send its
    small reply-first quota (0 on days 1–3, ≤3 on 4–7, ≤10 on 8–10, complete on day 11)."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.warmup_auto import process_warmup_accounts
        async with AsyncSessionLocal() as db:
            await process_warmup_accounts(db)
    run_async(_run())


@celery_app.task(name="tasks.process_mesh_warmup")
def task_process_mesh_warmup():
    """V17 PART 4 — automatic jittered AI mesh warm-up tick. Advances each enabled
    enrollment's state and runs one due, jittered action (webhook-only; never polling)."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.warmup_engine import run_warmup_tick
        from app.services.warmup_ai import build_warmup_ai_fn
        # V23 — connect the multi-provider AI key pool as the PRIMARY content source
        # (curated Persian pool remains the automatic fallback inside generate_mesh_message).
        async with AsyncSessionLocal() as db:
            await run_warmup_tick(db, ai_fn=build_warmup_ai_fn())
    run_async(_run())


@celery_app.task(name="tasks.process_helper_warmup")
def task_process_helper_warmup():
    """V25 PART 1 — automatic "human helpers" warm-up assist tick (ADDITIVE; separate from the
    mesh + group tracks). When the toggle is ON, the main warm account slowly asks ≤25 known
    helpers to greet cold numbers. Sends AT MOST one ask/reminder per tick (waking-hours +
    jittered rate gate). Webhook-only success detection; default OFF."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.warmup_helper_engine import run_helper_tick
        async with AsyncSessionLocal() as db:
            await run_helper_tick(db)
    run_async(_run())


@celery_app.task(name="tasks.process_cold_replies")
def task_process_cold_replies():
    """V29 «همکاری تیمی» PART 5 — send AT MOST one due cold-account contextual auto-reply per
    tick, fully gated (can_send_now + the cold account's 24h cooldown + the shared pacer). A cold
    account not yet eligible has its reply deferred. No-op when nothing is due."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.warmup_cold_reply import run_cold_reply_tick
        async with AsyncSessionLocal() as db:
            await run_cold_reply_tick(db)
    run_async(_run())


@celery_app.task(name="tasks.process_thank_yous")
def task_process_thank_yous():
    """V30 PART 5 — send AT MOST one due, DEFERRED thank-you per tick (staggered overflow from a
    burst of completions), gated by the 09:00–19:00 Tehran window + the sender health gate + the
    shared per-instance pacer. The first completion is thanked inline; only overflow lands here."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.warmup_thankyou import run_thankyou_tick
        async with AsyncSessionLocal() as db:
            await run_thankyou_tick(db)
    run_async(_run())


@celery_app.task(name="tasks.process_team_schedule")
def task_process_team_schedule():
    """V29 «همکاری تیمی» PART 7 — advance each enrolled cold account's 10-day ask schedule,
    creating due ask-steps (no two steps on one thread per day; waking hours; jittered). Gated on
    the cold account's existing 24h post-authorization cooldown. No-op until a cold account is
    enrolled and its cooldown has cleared."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.warmup_team_schedule import run_team_schedule_tick
        async with AsyncSessionLocal() as db:
            await run_team_schedule_tick(db)
    run_async(_run())


@celery_app.task(name="tasks.process_group_warmup")
def task_process_group_warmup():
    """V19 PART 4 — automatic group-placement tick (ADDITIVE to the message mesh; the mesh
    scheduler is untouched). Places cold numbers into selected admin groups on the fixed
    anti-ban schedule. Webhook-only; never polling."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.warmup_group_engine import run_group_warmup_tick
        async with AsyncSessionLocal() as db:
            await run_group_warmup_tick(db)
    run_async(_run())


@celery_app.task(name="tasks.warmup_safety_scan")
def task_warmup_safety_scan():
    """V17 PART 5 — reset/erosion detection. Restart warm-up (from Day 1) + alert for any
    enrolled number idle past the erosion (14d) / auto-logout (30d) thresholds."""
    async def _run():
        from datetime import datetime
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.warmup_mesh import WarmupEnrollment
        from app.services.warmup_state import WarmupState
        from app.services.warmup_killswitch import idle_reset_reason, on_block_or_logout, _alert
        now = datetime.utcnow()
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(WarmupEnrollment).where(WarmupEnrollment.is_enabled.is_(True))
            )).scalars().all()
            for enr in rows:
                anchor = enr.last_activity_at or enr.started_at
                if not anchor:
                    continue
                idle_days = (now - anchor).days
                reason = idle_reset_reason(idle_days)
                if reason and enr.state != WarmupState.BLOCKED_RESET.value:
                    await on_block_or_logout(db, enr, reason, now)
                    await _alert(db, f"بی‌فعالیتی {idle_days} روزه ({reason})؛ گرم‌سازی بازنشانی شد.",
                                 scope="number", instance_id=enr.instance_id, enrollment_id=enr.id)
            await db.commit()
    run_async(_run())


@celery_app.task(name="tasks.recheck_method_support")
def task_recheck_method_support():
    """V14 PART G — weekly re-probe of ONLY the safe, read-only methods (never the
    destructive ones), so newly-enabled plan entitlements get picked up automatically."""
    SAFE_METHODS = [
        ("getSettings", "get"), ("getStateInstance", "get"), ("getWaSettings", "get"),
        ("getContacts", "get"), ("getMessagesCount", "get"), ("showMessagesQueue", "get"),
        ("getWebhooksBufferCount", "get"), ("lastIncomingMessages", "get"),
        ("lastOutgoingMessages", "get"), ("getOutgoingStatuses", "get"),
        ("getIncomingStatuses", "get"), ("lastIncomingCalls", "get"), ("lastOutgoingCalls", "get"),
    ]
    async def _run():
        import httpx
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from app.services.capabilities import record_support
        from app.services import green_partner
        async with AsyncSessionLocal() as db:
            acc = (await db.execute(select(Account).where(Account.status == AccountStatus.active))).scalars().first()
            if acc:
                base = f"https://api.green-api.com/waInstance{acc.instance_id}"
                for method, _verb in SAFE_METHODS:
                    params = {"minutes": 60} if method.startswith("last") or method.startswith("get") and "Statuses" in method else None
                    try:
                        async with httpx.AsyncClient(timeout=20) as c:
                            r = await c.get(f"{base}/{method}/{acc.api_token}", params=params)
                        supported = True if 200 <= r.status_code < 300 else (False if r.status_code == 403 else None)
                        await record_support(db, method, supported, r.status_code)
                    except Exception:
                        continue
            # Partner getInstances (safe, read-only).
            if green_partner.is_configured():
                try:
                    await green_partner.get_instances()
                    await record_support(db, "getInstances", True, 200)
                except Exception:
                    pass
    run_async(_run())


@celery_app.task(name="tasks.sync_partner_instances")
def task_sync_partner_instances():
    """V14 F3 — reconcile local accounts with the Green API Partner list every 6h.
    No-op (logged) when no partner token is configured."""
    async def _s():
        from app.services import green_partner
        if not green_partner.is_configured():
            return
        from app.database import AsyncSessionLocal
        from app.services.partner_sync import sync_partner_instances
        async with AsyncSessionLocal() as db:
            await sync_partner_instances(db)
    run_async(_s())

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


@celery_app.task(name="tasks.check_status_schedules")
def task_check_status_schedules():
    """V11.4 — post any due scheduled statuses (day+time match, dedup per slot)."""
    from app.services.status_scheduler import check_and_post_due_statuses
    run_async(check_and_post_due_statuses())


@celery_app.task(name="tasks.resume_drip_campaigns")
def task_resume_drip_campaigns():
    """V13.8 — daily (start of send window): resume paused drip campaigns that still
    have pending contacts; the per-day Redis counter resets on the new Tehran date."""
    async def _r():
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.campaign import Campaign, CampaignStatus, CampaignContact, MessageStatus
        from app.services.drip import PAUSE_REASON
        resumed = []
        async with AsyncSessionLocal() as db:
            paused = (await db.execute(select(Campaign).where(
                Campaign.drip_enabled == True,
                Campaign.status == CampaignStatus.paused,
            ))).scalars().all()
            for c in paused:
                if c.pause_reason != PAUSE_REASON:
                    continue  # only resume drip-quota pauses, not other pauses
                has_pending = (await db.execute(select(CampaignContact).where(
                    CampaignContact.campaign_id == c.id,
                    CampaignContact.status == MessageStatus.pending,
                ).limit(1))).scalars().first()
                if not has_pending:
                    c.status = CampaignStatus.completed
                    continue
                c.status = CampaignStatus.running
                c.pause_reason = None
                c.drip_last_run_date = datetime.now(ZoneInfo("Asia/Tehran")).date()
                resumed.append(str(c.id))
            await db.commit()
        for cid in resumed:
            task_run_campaign.delay(cid)
        if resumed:
            print(f"[Drip] resumed {len(resumed)} drip campaign(s)")
    run_async(_r())


@celery_app.task(name="tasks.recheck_ai_keys")
def task_recheck_ai_keys():
    """V12 — re-test failed/rate-limited AI keys so they auto-recover once quota resets."""
    from app.services.ai_key_pool import recheck_stale_keys
    run_async(recheck_stale_keys())


@celery_app.task(name="tasks.join_all_links")
def task_join_all_links(account_id: str, instance_id: str, api_token: str, links: list):
    """V11.3 — best-effort join all registered links with one account. Records
    per-link status (joined/unsupported/error). links: [[link_id, invite_link, name], ...].
    Green API join-by-link is often unsupported (404/403) — recorded gracefully."""
    async def _j():
        import uuid as _uuid
        from datetime import datetime as _dt
        from app.database import AsyncSessionLocal
        from app.models.join_links import AccountJoinStatus
        from app.services.green_api import GreenAPIClient
        from sqlalchemy import select as sa_select
        client = GreenAPIClient(instance_id, api_token)
        acc_uuid = _uuid.UUID(account_id)
        for item in links:
            link_id, invite_link = item[0], item[1]
            res = await client.join_group_via_link(invite_link)
            if res.get("success"):
                status, err = "joined", None
            elif res.get("unsupported"):
                status, err = "unsupported", res.get("error")
            else:
                status, err = "error", res.get("error")
            async with AsyncSessionLocal() as db:
                existing = (await db.execute(sa_select(AccountJoinStatus).where(
                    AccountJoinStatus.account_id == acc_uuid,
                    AccountJoinStatus.link_id == _uuid.UUID(link_id),
                ))).scalar_one_or_none()
                if existing:
                    existing.status = status
                    existing.error = err
                    if status == "joined":
                        existing.joined_at = _dt.utcnow()
                else:
                    db.add(AccountJoinStatus(
                        account_id=acc_uuid, link_id=_uuid.UUID(link_id),
                        status=status, error=err,
                        joined_at=_dt.utcnow() if status == "joined" else None,
                    ))
                await db.commit()
            await asyncio.sleep(5)  # avoid rate limit between joins
    run_async(_j())


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
    # V35 PART 1 — the automatic daily WhatsApp Status post has been REMOVED. This task
    # previously auto-posted a public status at 10:00 Tehran every day (the unwanted
    # behaviour, and a ban risk). It now ONLY advances the legacy warm-up day counter
    # (days_active), which feeds the send-limit formula. It must never post any status.
    async def _w():
        from app.database import AsyncSessionLocal
        from app.models.account import Account, AccountStatus
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Account).where(Account.status == AccountStatus.active, Account.warmup_enabled == True))
            for account in result.scalars().all():
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
        from app.services.green_api import GreenAPIClient, GreenInstanceDeleted
        from sqlalchemy import select
        from datetime import datetime  # V38 — reconnect-rest anchor stamp
        async with AsyncSessionLocal() as db:
            newly_active = []  # V11.3 — accounts that just became authorized
            result = await db.execute(select(Account))
            for account in result.scalars().all():
                try:
                    client = GreenAPIClient(account.instance_id, account.api_token)
                    state = await client.get_state()
                    was_active = account.status == AccountStatus.active
                    if state == "authorized":
                        # V38 — anchor the 24h post-reconnect TC rest on a genuine reconnect
                        # (non-active → active), consistent with the webhook path.
                        if not was_active:
                            _ts = datetime.utcnow()
                            account.reconnected_at = _ts
                            account.connected_at = _ts   # V39 PART 1 — universal connect-cooldown anchor
                        account.status = AccountStatus.active
                        if not was_active:
                            newly_active.append(account)
                    elif state == "blocked":
                        account.status = AccountStatus.banned
                    elif state == "notAuthorized":
                        account.status = AccountStatus.disconnected
                except GreenInstanceDeleted:
                    # V36 — the instance was deleted in the Green API console. Auto-transition to a
                    # terminal, clearly-labeled status so the dashboard stops showing a stale red
                    # «disconnected» banner and instead offers «حذف از پلتفرم».
                    if account.status != AccountStatus.green_api_deleted:
                        account.status = AccountStatus.green_api_deleted
                except Exception:
                    pass
            await db.commit()
        # V11.3 — auto-join all registered links for accounts that just connected.
        if newly_active:
            from app.models.join_links import GroupJoinLink
            async with AsyncSessionLocal() as db:
                links = [(str(l.id), l.invite_link, l.name or "") for l in (await db.execute(
                    select(GroupJoinLink).where(GroupJoinLink.is_active == True)
                )).scalars().all()]
            if links:
                for account in newly_active:
                    task_join_all_links.delay(str(account.id), account.instance_id, account.api_token, links)
                    print(f"[AutoJoin] queued {len(links)} link joins for newly-active account {account.name}")
    run_async(_s())
