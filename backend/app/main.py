import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select
from app.database import engine, Base, AsyncSessionLocal
import app.models  # noqa: F401  (register all models on Base.metadata)

# B2 — structured logging (one place; modules use logging.getLogger("afrakala.*")).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("afrakala")
from app.api.v1 import (
    accounts, campaigns, contacts, webhook, dashboard,
    inbox, groups, statuses, templates, queue, blacklist,
    keyword_rules, account_schedules,
    journals, files as files_router,
    contact_groups, wa_collections, reporting as reporting_router,
    join_links, status_schedules, ai_keys,
    partner, messages, incidents, calls,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS polling_enabled boolean DEFAULT false"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS is_deleted boolean DEFAULT false"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS edited_text text"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS original_message_id varchar(200)"))
        ddl = [
            # account_send_config
            """CREATE TABLE IF NOT EXISTS account_send_configs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid UNIQUE NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                min_delay_seconds integer NOT NULL DEFAULT 45,
                max_delay_seconds integer NOT NULL DEFAULT 110,
                created_at timestamp DEFAULT now(),
                updated_at timestamp DEFAULT now()
            )""",
            # keyword_rules
            """CREATE TABLE IF NOT EXISTS keyword_rules (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                keyword varchar(500) NOT NULL,
                reply_message text NOT NULL,
                match_type varchar(20) NOT NULL DEFAULT 'contains',
                scope varchar(20) NOT NULL DEFAULT 'both',
                is_active boolean NOT NULL DEFAULT true,
                use_count integer NOT NULL DEFAULT 0,
                created_at timestamp DEFAULT now()
            )""",
            # account_hour_schedule
            """CREATE TABLE IF NOT EXISTS account_hour_schedules (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                hour_start integer NOT NULL,
                hour_end integer NOT NULL,
                max_per_hour integer NOT NULL DEFAULT 0,
                gpt_prompt text,
                message_template text,
                is_active boolean NOT NULL DEFAULT true,
                created_at timestamp DEFAULT now(),
                UNIQUE (account_id, hour_start, hour_end)
            )""",
            # campaigns: add group campaign columns
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS campaign_scope varchar(20) DEFAULT 'pv'",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS group_ids text",
        ]
        for stmt in ddl:
            await conn.execute(text(stmt))
        ddl_v4 = [
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS call_status varchar(50)",
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS button_reply_id varchar(200)",
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS button_reply_title varchar(500)",
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS poll_votes text",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS quota_exceeded_at timestamp",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS pause_reason text",
            """CREATE TABLE IF NOT EXISTS chat_journals (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                instance_id varchar(50),
                chat_id varchar(100),
                direction varchar(10),
                message_type varchar(50),
                text_content text,
                file_url text,
                green_message_id varchar(200),
                timestamp timestamp,
                fetched_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS uploaded_files (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                original_filename varchar(500),
                green_api_url text,
                uploaded_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS ai_usage_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                provider varchar(50) NOT NULL,
                model varchar(100),
                prompt_tokens integer DEFAULT 0,
                completion_tokens integer DEFAULT 0,
                total_tokens integer DEFAULT 0,
                success boolean DEFAULT true,
                error_text text,
                used_at timestamp DEFAULT now()
            )""",
        ]
        for stmt in ddl_v4:
            await conn.execute(text(stmt))
        ddl_v5 = [
            """CREATE TABLE IF NOT EXISTS contact_groups (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(200) NOT NULL,
                description text,
                color varchar(20) DEFAULT '#25D366',
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS contact_group_members (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                group_id uuid NOT NULL REFERENCES contact_groups(id) ON DELETE CASCADE,
                contact_id uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                UNIQUE(group_id, contact_id)
            )""",
            """CREATE TABLE IF NOT EXISTS wa_group_collections (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(200) NOT NULL,
                description text,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS wa_group_collection_members (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                collection_id uuid NOT NULL REFERENCES wa_group_collections(id) ON DELETE CASCADE,
                group_chat_id varchar(200) NOT NULL,
                group_name varchar(200),
                UNIQUE(collection_id, group_chat_id)
            )""",
            """CREATE TABLE IF NOT EXISTS emergency_contacts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(100),
                phone varchar(20) NOT NULL,
                purpose varchar(100) DEFAULT 'alert',
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS report_subscribers (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                phone varchar(20) NOT NULL UNIQUE,
                name varchar(100),
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS daily_send_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                date date NOT NULL DEFAULT CURRENT_DATE,
                account_id uuid REFERENCES accounts(id),
                account_name varchar(100),
                campaign_name varchar(200),
                recipient_phone varchar(20),
                recipient_name varchar(200),
                status varchar(50),
                sent_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS product_mention_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                product_name varchar(500),
                product_id varchar(100),
                sender_phone varchar(20),
                sender_name varchar(200),
                group_name varchar(200),
                group_chat_id varchar(200),
                instance_id varchar(50),
                message_text text,
                mentioned_at timestamp DEFAULT now()
            )""",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS description text",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS append_date boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS append_seller_name boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS seller_name varchar(200)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS append_seller_phone boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS seller_phone varchar(20)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS seller_phone2 varchar(20)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS emoji_level varchar(20) DEFAULT 'medium'",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS contact_group_id uuid",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS wa_collection_id uuid",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_label_filter varchar(200)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS is_always_on boolean DEFAULT false",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS emergency_phones text",
        ]
        for stmt in ddl_v5:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V5] {e}")
        ddl_v6 = [
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_host varchar(200)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_port integer",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_login varchar(100)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_password varchar(200)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS proxy_enabled boolean DEFAULT false",
            """CREATE TABLE IF NOT EXISTS disappearing_chat_settings (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                chat_id varchar(200) NOT NULL,
                ephemeral integer NOT NULL DEFAULT 0,
                set_at timestamp DEFAULT now(),
                UNIQUE(account_id, chat_id)
            )""",
            """CREATE TABLE IF NOT EXISTS wa_blocked_contacts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                phone varchar(20) NOT NULL,
                synced_at timestamp DEFAULT now(),
                UNIQUE(account_id, phone)
            )""",
        ]
        for stmt in ddl_v6:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V6] {e}")
        ddl_v7 = [
            "ALTER TABLE account_hour_schedules ADD COLUMN IF NOT EXISTS include_products boolean DEFAULT false",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_default boolean DEFAULT false",
            "ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS chat_type varchar(20) DEFAULT 'group'",
            "ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS description text",
            "ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS synced_at timestamp DEFAULT now()",
        ]
        ddl_v8 = [
            # Feature 37: parallel account sending
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS parallel_accounts boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS max_parallel_accounts integer DEFAULT 1",
            # Feature 39: per-account send limits with Meta standards
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS max_daily_absolute integer DEFAULT 200",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS incoming_ratio_multiplier numeric DEFAULT 0.5",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS max_sends_per_minute numeric DEFAULT 2.0",
            # Feature 40/41: group admin tracking
            "ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS is_admin boolean DEFAULT false",
            "ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS participant_count integer DEFAULT 0",
            # Feature 42: hide price option in campaigns
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS show_product_prices boolean DEFAULT true",
        ]
        ddl_v9 = [
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS group_source varchar(500)",
        ]
        # A4 — indexes on hot query columns (idempotent). Column names verified
        # against the models (ai_usage_logs uses used_at, not created_at).
        ddl_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_contacts_blacklisted ON contacts(blacklisted)",
            "CREATE INDEX IF NOT EXISTS idx_contacts_has_whatsapp ON contacts(has_whatsapp)",
            "CREATE INDEX IF NOT EXISTS idx_contacts_created ON contacts(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_campaign ON campaign_contacts(campaign_id)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_status ON campaign_contacts(status)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_composite ON campaign_contacts(campaign_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_msgid ON campaign_contacts(green_api_message_id)",
            "CREATE INDEX IF NOT EXISTS idx_inbox_instance ON inbox_messages(instance_id)",
            "CREATE INDEX IF NOT EXISTS idx_inbox_timestamp ON inbox_messages(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_inbox_sender ON inbox_messages(sender_phone)",
            "CREATE INDEX IF NOT EXISTS idx_wa_groups_account ON whatsapp_groups(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_wa_groups_admin ON whatsapp_groups(is_admin)",
            "CREATE INDEX IF NOT EXISTS idx_daily_send_logs_date ON daily_send_logs(date)",
            "CREATE INDEX IF NOT EXISTS idx_ai_usage_used ON ai_usage_logs(used_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)",
        ]
        for stmt in ddl_v7:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V7] {e}")
        for stmt in ddl_v8:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V8] {e}")
        for stmt in ddl_v9:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V9] {e}")
        for stmt in ddl_indexes:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[IDX] {e}")
        ddl_v11 = [
            """CREATE TABLE IF NOT EXISTS status_schedules (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                name varchar(200),
                status_type varchar(50) NOT NULL,
                content_type varchar(30) DEFAULT 'text',
                intro_subtype varchar(50),
                custom_text text,
                show_price boolean DEFAULT false,
                include_image boolean DEFAULT false,
                include_caption boolean DEFAULT true,
                image_url text,
                product_selection varchar(20) DEFAULT 'random',
                product_pool jsonb,
                product_pick_count integer DEFAULT 3,
                days_of_week jsonb,
                specific_dates jsonb,
                times jsonb,
                is_active boolean DEFAULT true,
                next_run_at timestamp,
                last_run_at timestamp,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS group_join_links (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(300),
                invite_link text NOT NULL,
                link_type varchar(20) DEFAULT 'group',
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS account_join_status (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                link_id uuid REFERENCES group_join_links(id) ON DELETE CASCADE,
                status varchar(30) DEFAULT 'pending',
                joined_at timestamp,
                error text,
                UNIQUE(account_id, link_id)
            )""",
        ]
        for stmt in ddl_v11:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V11] {e}")
        ddl_v12 = [
            """CREATE TABLE IF NOT EXISTS ai_keys (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                provider varchar(30) NOT NULL,
                api_key text NOT NULL,
                label varchar(200),
                is_active boolean DEFAULT true,
                status varchar(30) DEFAULT 'unknown',
                last_checked_at timestamp,
                last_error text,
                success_count integer DEFAULT 0,
                fail_count integer DEFAULT 0,
                rate_limited_until timestamp,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_ai_keys_provider ON ai_keys(provider)",
            "CREATE INDEX IF NOT EXISTS idx_ai_keys_active ON ai_keys(is_active)",
        ]
        for stmt in ddl_v12:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V12] {e}")
        # Campaign message customization (opening line, per-group products, opt-out)
        ddl_campaign_custom = [
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS opening_mode varchar(20) DEFAULT 'ai'",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS opening_line varchar(500)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS opening_variants jsonb",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_variation_mode varchar(20) DEFAULT 'same'",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS products_per_group integer DEFAULT 3",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_weights jsonb",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS include_opt_out boolean DEFAULT true",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS opt_out_text varchar(300)",
        ]
        for stmt in ddl_campaign_custom:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL campaign-custom] {e}")
        # V13.1 — A/B message testing
        ddl_v13_ab = [
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS ab_test_enabled boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS variant_b_prompt text",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS variant_b_template text",
            "ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS ab_variant varchar(1)",
        ]
        for stmt in ddl_v13_ab:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V13.1] {e}")
        # V13.5 — rich WhatsApp formatting
        try:
            await conn.execute(text("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS use_rich_formatting boolean DEFAULT false"))
        except Exception as e:
            print(f"[DDL V13.5] {e}")
        # V13.2 — smart health-weighted account rotation
        try:
            await conn.execute(text("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS smart_rotation boolean DEFAULT false"))
        except Exception as e:
            print(f"[DDL V13.2] {e}")
        # V13.4 — auto opt-out log
        try:
            await conn.execute(text("""CREATE TABLE IF NOT EXISTS opt_out_log (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                phone varchar(20),
                reason varchar(50),
                campaign_id uuid,
                created_at timestamp DEFAULT now()
            )"""))
        except Exception as e:
            print(f"[DDL V13.4] {e}")
        # V13.7 — campaign ROI tracking
        ddl_v13_roi = [
            "ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS replied boolean DEFAULT false",
            "ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS outcome varchar(30)",
            "ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS outcome_note text",
        ]
        for stmt in ddl_v13_roi:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V13.7] {e}")
        # V13.8 — drip sending
        ddl_v13_drip = [
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS drip_enabled boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS drip_per_day integer DEFAULT 50",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS drip_last_run_date date",
        ]
        for stmt in ddl_v13_drip:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V13.8] {e}")
        # V14 PART A — Green API Partner (instances) + PART G capability registry.
        ddl_v14_partner = [
            """CREATE TABLE IF NOT EXISTS partner_instance_log (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                id_instance bigint,
                action varchar(30),          -- created | deleted | synced
                detail text,
                created_at timestamp DEFAULT now()
            )""",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS created_via_partner boolean DEFAULT false",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS partner_created_at timestamp",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS profile_picture_url text",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS tariff varchar(40)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_orphaned boolean DEFAULT false",
            # F2 — allow soft-deleting a partner-deleted instance (PG15 allows this in a tx;
            # the new value is not used in this same transaction).
            "ALTER TYPE accountstatus ADD VALUE IF NOT EXISTS 'deleted'",
            # PART G — capability registry (seeded by the PHASE 0 probe, updated on every call).
            """CREATE TABLE IF NOT EXISTS method_support (
                method varchar(60) PRIMARY KEY,
                supported boolean,                -- null = unknown/not probed
                last_status_code integer,
                last_checked timestamp DEFAULT now(),
                note text
            )""",
        ]
        for stmt in ddl_v14_partner:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V14 partner] {e}")
        # V14 PART B — interactive & rich messaging.
        ddl_v14_partb = [
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS use_interactive_buttons boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS buttons_config jsonb",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS button_header text",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS button_footer text",
            """CREATE TABLE IF NOT EXISTS button_replies (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id uuid,
                contact_phone varchar(20),
                chat_id varchar(60),
                button_id varchar(20),
                button_text text,
                message_id varchar(80),
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_button_replies_campaign ON button_replies(campaign_id)",
            """CREATE TABLE IF NOT EXISTS button_auto_replies (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                button_id varchar(20),
                button_text text,
                reply_text text NOT NULL,
                enabled boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS message_reactions (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                chat_id varchar(60),
                sender_phone varchar(20),
                sender_name text,
                emoji text,
                reacted_message_id varchar(80),
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS saved_contact_cards (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                label varchar(100) NOT NULL,
                phone_contact varchar(20) NOT NULL,
                first_name varchar(100),
                last_name varchar(100),
                company varchar(100) DEFAULT 'افراکالا',
                is_default boolean DEFAULT false,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS saved_locations (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name text NOT NULL,
                address text,
                latitude double precision NOT NULL,
                longitude double precision NOT NULL,
                is_default boolean DEFAULT false,
                created_at timestamp DEFAULT now()
            )""",
        ]
        for stmt in ddl_v14_partb:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V14 partB] {e}")
        # V14 PART C — message control (edit/delete/recall).
        ddl_v14_partc = [
            "ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS is_edited boolean DEFAULT false",
            "ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS edited_at timestamp",
            "ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS recalled boolean DEFAULT false",
        ]
        for stmt in ddl_v14_partc:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V14 partC] {e}")
        # V14 PART D — chat & profile.
        ddl_v14_partd = [
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS archived boolean DEFAULT false",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS profile_picture_url text",  # (also in PART A)
            """CREATE TABLE IF NOT EXISTS contact_info_cache (
                chat_id varchar(60) PRIMARY KEY,
                payload jsonb,
                fetched_at timestamp DEFAULT now()
            )""",
        ]
        for stmt in ddl_v14_partd:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V14 partD] {e}")
        # V14 PART E — statuses & groups.
        ddl_v14_parte = [
            "ALTER TABLE status_schedules ADD COLUMN IF NOT EXISTS content_type varchar(20) DEFAULT 'text'",
            "ALTER TABLE status_schedules ADD COLUMN IF NOT EXISTS voice_file_url text",
            "ALTER TABLE status_schedules ADD COLUMN IF NOT EXISTS target_participants jsonb",
        ]
        for stmt in ddl_v14_parte:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V14 partE] {e}")
        # V14 PART F — safety (yellowCard incidents) & call logs.
        ddl_v14_partf = [
            """CREATE TABLE IF NOT EXISTS account_incidents (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid,
                id_instance bigint,
                incident_type varchar(30),
                detected_via varchar(20),
                severity varchar(10),
                auto_actions jsonb,
                campaigns_paused jsonb,
                queue_snapshot jsonb,
                resolved boolean DEFAULT false,
                resolved_at timestamp,
                resolved_by varchar(20),
                notes text,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_incidents_account ON account_incidents(account_id, created_at DESC)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS throttle_factor double precision DEFAULT 1.0",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS throttle_until timestamp",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS cooldown_until timestamp",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS incident_count_7d integer DEFAULT 0",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS last_incident_at timestamp",
            "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS first_messaged_at timestamp",
            """CREATE TABLE IF NOT EXISTS call_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid,
                direction varchar(10),
                from_phone varchar(20),
                status varchar(20),
                contact_name text,
                called_at timestamp,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_call_logs_time ON call_logs(called_at DESC)",
        ]
        for stmt in ddl_v14_partf:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V14 partF] {e}")
    # Startup config sanity checks
    from app.config import settings as _settings
    if not _settings.supabase_anon_key:
        logger.warning("SUPABASE_ANON_KEY is empty — set it in .env; product prices will be unavailable.")

    # B1.3 — resume campaigns left in 'running' after a restart. The per-campaign
    # Redis lock in run_campaign makes this safe (a re-queue for an already-active
    # campaign is skipped instead of double-sending).
    try:
        from app.models.campaign import Campaign, CampaignStatus
        from app.database import AsyncSessionLocal
        from app.workers.tasks import task_run_campaign
        async with AsyncSessionLocal() as db:
            running = (await db.execute(
                select(Campaign).where(Campaign.status == CampaignStatus.running)
            )).scalars().all()
            for c in running:
                task_run_campaign.delay(str(c.id))
            if running:
                logger.info("Startup: re-queued %d running campaign(s)", len(running))
    except Exception as e:
        logger.warning("Startup campaign resume failed (non-fatal): %s", e)
    yield

app = FastAPI(title="Afrakala WhatsApp Sender", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [
    accounts.router, campaigns.router, contacts.router, webhook.router,
    dashboard.router, inbox.router, groups.router, statuses.router,
    templates.router, queue.router, blacklist.router,
    keyword_rules.router, account_schedules.router,
    journals.router, files_router.router,
    contact_groups.router, wa_collections.router, reporting_router.router,
    join_links.router, status_schedules.router, ai_keys.router,
    partner.router, messages.router, incidents.router, calls.router,
]:
    app.include_router(router, prefix="/api/v1")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """B2 — log any unhandled error with a stack trace and return clean JSON.
    (FastAPI's own handlers for HTTPException / validation errors still apply.)"""
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/health/detailed")
async def health_detailed():
    """B2 — deep health check: DB, Redis, and Celery worker heartbeat."""
    result = {"status": "ok", "checks": {}}

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        result["checks"]["database"] = "ok"
    except Exception as e:
        result["checks"]["database"] = f"error: {e}"
        result["status"] = "degraded"

    try:
        from app.services import redis_rate_limiter
        r = await redis_rate_limiter.get_redis()
        await r.ping()
        result["checks"]["redis"] = "ok"
    except Exception as e:
        result["checks"]["redis"] = f"error: {e}"
        result["status"] = "degraded"

    try:
        from app.workers.celery_app import celery_app
        pong = celery_app.control.ping(timeout=1.0)
        workers = [list(w.keys())[0] for w in pong] if pong else []
        result["checks"]["workers"] = workers or "no workers responding"
        if not workers:
            result["status"] = "degraded"
    except Exception as e:
        result["checks"]["workers"] = f"error: {e}"
        result["status"] = "degraded"

    return result
