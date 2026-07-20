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
    capabilities as capabilities_router,
    adlinks, warmup, warmup_helpers,
    group_monitor, telegram, onboarding,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # V36 — create_all never ALTERs an existing PG enum, so add the new account status value
        # idempotently (PG 15 allows ADD VALUE inside this transaction as long as it isn't used here).
        await conn.execute(text("ALTER TYPE accountstatus ADD VALUE IF NOT EXISTS 'green_api_deleted'"))
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
        # V15 — campaign UX (product detail level, chosen account when parallel off).
        ddl_v15 = [
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_detail_level varchar(20) DEFAULT 'medium'",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS selected_account_id uuid",
            # Item 26 — managed auto warm-up
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS auto_warmup boolean DEFAULT false",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS warmup_started_at timestamp",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS warmup_completed boolean DEFAULT false",
        ]
        # V16 PART 3 — advertising links + campaign append settings.
        ddl_v16 = [
            """CREATE TABLE IF NOT EXISTS advertising_links (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                url text NOT NULL,
                title varchar(200) NOT NULL,
                link_type varchar(20) DEFAULT 'other',
                weight integer DEFAULT 5,
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS append_links boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS links_count integer DEFAULT 1",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS links_mode varchar(20) DEFAULT 'weighted'",
            # V16 PART 5 — editable warm-up phrase pool
            """CREATE TABLE IF NOT EXISTS warmup_phrases (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                text text NOT NULL,
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
        ]
        ddl_v15 += ddl_v16
        for stmt in ddl_v15:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V15] {e}")
        # V16 PART 5 — seed the warm-up phrase pool once (only if empty).
        try:
            from app.services.warmup_auto import DEFAULT_PHRASES
            existing = (await conn.execute(text("SELECT count(*) FROM warmup_phrases"))).scalar() or 0
            if existing == 0:
                for ph in DEFAULT_PHRASES:
                    await conn.execute(text(
                        "INSERT INTO warmup_phrases (id, text, is_active, created_at) "
                        "VALUES (gen_random_uuid(), :t, true, now())"), {"t": ph})
        except Exception as e:
            print(f"[Seed warmup_phrases] {e}")
        # ── V17 PART 1 — per-campaign typing simulation (OFF by default) ────
        ddl_v17_part1 = [
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS typing_simulation boolean DEFAULT false",
        ]
        # ── V17 PART 2 — mesh warm-up schema (enrollment state machine + edges + log) ──
        ddl_v17_part2 = [
            """CREATE TABLE IF NOT EXISTS warmup_enrollment (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                instance_id varchar(50) NOT NULL,
                phone varchar(20),
                state varchar(20) NOT NULL DEFAULT 'ENROLLED',
                day_index integer NOT NULL DEFAULT 0,
                started_at timestamp,
                authorized_at timestamp,
                last_activity_at timestamp,
                sent_today integer NOT NULL DEFAULT 0,
                received_today integer NOT NULL DEFAULT 0,
                reply_ratio double precision NOT NULL DEFAULT 0,
                next_action_at timestamp,
                is_enabled boolean NOT NULL DEFAULT false,
                rest_until timestamp,
                counters_date date,
                config_json text,
                created_at timestamp DEFAULT now(),
                updated_at timestamp DEFAULT now(),
                UNIQUE (instance_id)
            )""",
            """CREATE TABLE IF NOT EXISTS warmup_mesh_edge (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                new_instance_id varchar(50) NOT NULL,
                peer_instance_id varchar(50) NOT NULL,
                direction varchar(20) NOT NULL DEFAULT 'bidirectional',
                handshake_state varchar(20) NOT NULL DEFAULT 'none',
                saved_as_contact_new boolean NOT NULL DEFAULT false,
                saved_as_contact_peer boolean NOT NULL DEFAULT false,
                last_msg_at timestamp,
                msg_count integer NOT NULL DEFAULT 0,
                created_at timestamp DEFAULT now(),
                UNIQUE (new_instance_id, peer_instance_id)
            )""",
            """CREATE TABLE IF NOT EXISTS warmup_event_log (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                enrollment_id uuid,
                edge_id uuid,
                event_type varchar(20) NOT NULL,
                content_hash varchar(64),
                delivery_status varchar(30),
                payload_json text,
                created_at timestamp DEFAULT now()
            )""",
        ]
        # ── V17 PART 3 — manual warm-peer flag on accounts ─────────────────
        ddl_v17_part3 = [
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_warm_peer boolean DEFAULT false",
        ]
        # ── V19 — group-based warm-up schema + manual link vault ───────────
        ddl_v19 = [
            """CREATE TABLE IF NOT EXISTS warmup_group_target (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                warm_instance_id varchar(50) NOT NULL,
                group_id varchar(80) NOT NULL,
                group_subject varchar(300),
                is_selected boolean NOT NULL DEFAULT true,
                created_at timestamp DEFAULT now(),
                UNIQUE (warm_instance_id, group_id)
            )""",
            """CREATE TABLE IF NOT EXISTS warmup_group_membership (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                cold_instance_id varchar(50) NOT NULL,
                warm_instance_id varchar(50) NOT NULL,
                group_id varchar(80) NOT NULL,
                status varchar(20) NOT NULL DEFAULT 'pending',
                attempts integer NOT NULL DEFAULT 0,
                last_attempt_at timestamp,
                added_at timestamp,
                error_reason text,
                created_at timestamp DEFAULT now(),
                UNIQUE (cold_instance_id, group_id)
            )""",
            """CREATE TABLE IF NOT EXISTS warmup_link_vault (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                group_name varchar(300),
                invite_link text NOT NULL,
                notes text,
                created_at timestamp DEFAULT now()
            )""",
        ]
        for stmt in ddl_v17_part1 + ddl_v17_part2 + ddl_v17_part3 + ddl_v19:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V17] {e}")
        # ── V25 PART 1 — "human helpers" warm-up assist (≤25 known people) ──
        ddl_v25 = [
            """CREATE TABLE IF NOT EXISTS warmup_helper (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(120) NOT NULL,
                phone varchar(20) NOT NULL,
                is_active boolean NOT NULL DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_phone ON warmup_helper(phone)",
            """CREATE TABLE IF NOT EXISTS warmup_helper_task (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                helper_id uuid NOT NULL,
                cold_instance_id varchar(50) NOT NULL,
                status varchar(20) NOT NULL DEFAULT 'pending',
                asked_at timestamp,
                reminded_at timestamp,
                done_at timestamp,
                attempts integer NOT NULL DEFAULT 0,
                created_at timestamp DEFAULT now(),
                UNIQUE (helper_id, cold_instance_id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_task_helper ON warmup_helper_task(helper_id)",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_task_cold ON warmup_helper_task(cold_instance_id)",
            """CREATE TABLE IF NOT EXISTS warmup_helper_config (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                is_enabled boolean NOT NULL DEFAULT false,
                next_ask_at timestamp,
                updated_at timestamp DEFAULT now()
            )""",
        ]
        for stmt in ddl_v25:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V25] {e}")
        # ── V28 — generalize the helper assist into a multi-sender outreach assistant ──
        ddl_v28 = [
            "ALTER TABLE warmup_helper ADD COLUMN IF NOT EXISTS sender_instance_id varchar(50)",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_sender ON warmup_helper(sender_instance_id)",
            "ALTER TABLE warmup_helper_config ADD COLUMN IF NOT EXISTS soft_warning_threshold integer NOT NULL DEFAULT 30",
            """CREATE TABLE IF NOT EXISTS outreach_brief (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                sender_instance_id varchar(50) NOT NULL,
                brief_text text NOT NULL,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_outreach_brief_sender ON outreach_brief(sender_instance_id)",
            # Backfill any pre-V28 helper rows to the main account (is_default → first active),
            # so lists scoped by sender never silently drop legacy contacts. No-op when empty.
            """UPDATE warmup_helper SET sender_instance_id = COALESCE(
                   (SELECT instance_id FROM accounts WHERE is_default = true LIMIT 1),
                   (SELECT instance_id FROM accounts WHERE status = 'active' ORDER BY created_at LIMIT 1)
               ) WHERE sender_instance_id IS NULL""",
        ]
        for stmt in ddl_v28:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V28] {e}")
        # ── V29 «همکاری تیمی» (Team Collaboration) — EXTENDS V28's warmup_helper* schema
        #    (no parallel team_collab_* tables). Rich personnel profile on warmup_helper, a
        #    real DB-level unique on the (contact × cold) pairing, per-sender enable flag, an
        #    is_current brief flag, the conversation-thread table, per-cold-account enrollment,
        #    and the dedicated Shamsi-dated event log. ──
        ddl_v29 = [
            # PART 1 — rich personnel profile (all nullable; never breaks legacy rows).
            "ALTER TABLE warmup_helper ADD COLUMN IF NOT EXISTS job_title varchar(200)",
            "ALTER TABLE warmup_helper ADD COLUMN IF NOT EXISTS years_experience integer",
            "ALTER TABLE warmup_helper ADD COLUMN IF NOT EXISTS personal_benefit_note text",
            "ALTER TABLE warmup_helper ADD COLUMN IF NOT EXISTS phone_secondary varchar(20)",
            # PART 1 — promote the (helper, cold) pairing to a REAL unique constraint (was only
            # app-enforced on tables created before the V25 CREATE included it). Idempotent via a
            # unique INDEX so re-running startup never errors.
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_warmup_helper_task_pair "
            "ON warmup_helper_task(helper_id, cold_instance_id)",
            # PART 1 — is_current on the append-only brief (exactly one active per sender).
            "ALTER TABLE outreach_brief ADD COLUMN IF NOT EXISTS is_current boolean NOT NULL DEFAULT true",
            # PART 1 — per-sender enable flag (the global toggle stays the master switch).
            """CREATE TABLE IF NOT EXISTS warmup_sender_config (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                sender_instance_id varchar(50) NOT NULL UNIQUE,
                is_enabled boolean NOT NULL DEFAULT true,
                updated_at timestamp DEFAULT now()
            )""",
            # PART 3 — conversation threads, keyed by (helper, cold_instance). One row per pair
            # that ever had an ask-step; carries the running topic so follow-ups continue it.
            """CREATE TABLE IF NOT EXISTS warmup_helper_thread (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                helper_id uuid NOT NULL,
                cold_instance_id varchar(50) NOT NULL,
                topic_summary text,
                step_count integer NOT NULL DEFAULT 0,
                status varchar(20) NOT NULL DEFAULT 'active',
                last_step_at timestamp,
                created_at timestamp DEFAULT now(),
                UNIQUE (helper_id, cold_instance_id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_thread_helper ON warmup_helper_thread(helper_id)",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_thread_cold ON warmup_helper_thread(cold_instance_id)",
            # PART 5 — scheduled (never instant) cold-account auto-reply, gated on send.
            "ALTER TABLE warmup_helper_thread ADD COLUMN IF NOT EXISTS awaiting_reply boolean NOT NULL DEFAULT false",
            "ALTER TABLE warmup_helper_thread ADD COLUMN IF NOT EXISTS pending_reply_at timestamp",
            # V30 PART 5 — scheduled, staggered thank-you (sent by run_thankyou_tick, not inline).
            "ALTER TABLE warmup_helper_thread ADD COLUMN IF NOT EXISTS awaiting_thankyou boolean NOT NULL DEFAULT false",
            "ALTER TABLE warmup_helper_thread ADD COLUMN IF NOT EXISTS pending_thankyou_at timestamp",
            # PART 4 — admin alerts raised when a forbidden/sensitive word appears in a thread.
            """CREATE TABLE IF NOT EXISTS warmup_thread_alert (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id uuid NOT NULL,
                helper_id uuid,
                cold_instance_id varchar(50),
                keyword varchar(120),
                direction varchar(20),
                message_excerpt text,
                acknowledged boolean NOT NULL DEFAULT false,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_warmup_thread_alert_thread ON warmup_thread_alert(thread_id)",
            # PART 7 — per-cold-account «عضویت در همکاری تیمی» enrollment (distinct from the mesh
            # warm-up enrollment), with its own 10-day cycle clock.
            """CREATE TABLE IF NOT EXISTS warmup_team_enrollment (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                cold_instance_id varchar(50) NOT NULL UNIQUE,
                is_enabled boolean NOT NULL DEFAULT false,
                enrolled_at timestamp,
                day_index integer NOT NULL DEFAULT 0,
                created_at timestamp DEFAULT now(),
                updated_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_warmup_team_enrollment_cold ON warmup_team_enrollment(cold_instance_id)",
            # PART 9 — dedicated Team-Collaboration event log (parallel to inbox/send-queue).
            """CREATE TABLE IF NOT EXISTS warmup_helper_log (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                event_type varchar(20) NOT NULL,
                from_instance_id varchar(50),
                to_phone varchar(20),
                helper_id uuid,
                sender_instance_id varchar(50),
                cold_instance_id varchar(50),
                thread_id uuid,
                message_sent text,
                message_received text,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_log_sender ON warmup_helper_log(sender_instance_id)",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_log_cold ON warmup_helper_log(cold_instance_id)",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_log_helper ON warmup_helper_log(helper_id)",
            "CREATE INDEX IF NOT EXISTS ix_warmup_helper_log_created ON warmup_helper_log(created_at)",
        ]
        for stmt in ddl_v29:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V29] {e}")
        # ── V33 PART 2 — DB-level backstop for the 2-distinct-cold-per-contact ceiling. The
        #    service layer (assign_cold_account / ensure_helper_tasks / escalate_after_completion)
        #    already refuses a 3rd distinct cold; this trigger makes the invariant hold at the DB so no
        #    path (or future code) can ever pair one contact to more than 2 distinct cold accounts.
        #    The UNIQUE(helper_id, cold_instance_id) index still blocks exact-duplicate pairs. ──
        ddl_v33 = [
            """CREATE OR REPLACE FUNCTION enforce_warmup_cold_ceiling() RETURNS trigger AS $$
            DECLARE
                distinct_colds integer;
            BEGIN
                SELECT count(DISTINCT cold_instance_id) INTO distinct_colds
                FROM warmup_helper_task
                WHERE helper_id = NEW.helper_id
                  AND cold_instance_id <> NEW.cold_instance_id;
                IF distinct_colds >= 2 THEN
                    RAISE EXCEPTION 'warmup_helper_task cold ceiling: contact % already assigned to 2 distinct cold accounts', NEW.helper_id
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql""",
            "DROP TRIGGER IF EXISTS trg_warmup_cold_ceiling ON warmup_helper_task",
            """CREATE TRIGGER trg_warmup_cold_ceiling
                BEFORE INSERT ON warmup_helper_task
                FOR EACH ROW EXECUTE FUNCTION enforce_warmup_cold_ceiling()""",
        ]
        for stmt in ddl_v33:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V33] {e}")
        # ── V33 PART 3 — remove any orphaned task/thread rows (helper_id → a deleted contact), then
        #    add a FK backstop so deleting a contact can never leave orphans again. The service layer
        #    additionally BLOCKS deleting a contact that still has ACTIVE tasks (Persian message); a
        #    contact with only terminal tasks is deletable and the FK CASCADE cleans its rows. The
        #    DELETEs must run BEFORE the ADD CONSTRAINT (a FK cannot be added while orphans exist). ──
        ddl_v33_part3 = [
            "DELETE FROM warmup_helper_task WHERE helper_id NOT IN (SELECT id FROM warmup_helper)",
            "DELETE FROM warmup_helper_thread WHERE helper_id NOT IN (SELECT id FROM warmup_helper)",
            """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_warmup_helper_task_helper') THEN
                    ALTER TABLE warmup_helper_task ADD CONSTRAINT fk_warmup_helper_task_helper
                        FOREIGN KEY (helper_id) REFERENCES warmup_helper(id) ON DELETE CASCADE;
                END IF;
            END $$""",
            """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_warmup_helper_thread_helper') THEN
                    ALTER TABLE warmup_helper_thread ADD CONSTRAINT fk_warmup_helper_thread_helper
                        FOREIGN KEY (helper_id) REFERENCES warmup_helper(id) ON DELETE CASCADE;
                END IF;
            END $$""",
        ]
        for stmt in ddl_v33_part3:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V33 P3] {e}")
        # ── V33 PART 4 — reminder_count on warmup_helper_task: bounds reminders at exactly 2, then
        #    the task goes terminal `no_response` (no 3rd reminder / re-ask). ──
        ddl_v33_part4 = [
            "ALTER TABLE warmup_helper_task ADD COLUMN IF NOT EXISTS reminder_count integer NOT NULL DEFAULT 0",
        ]
        for stmt in ddl_v33_part4:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V33 P4] {e}")
        # ── V26 — group monitoring (listener) + voice transcription schema ──
        ddl_v26 = [
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_listener boolean DEFAULT false",
            """CREATE TABLE IF NOT EXISTS monitored_group (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                listener_instance_id varchar(50) NOT NULL,
                group_id varchar(80) NOT NULL,
                group_name varchar(300),
                is_monitored boolean NOT NULL DEFAULT true,
                auto_reply_enabled boolean NOT NULL DEFAULT false,
                conversation_mode varchar(20) NOT NULL DEFAULT 'off',
                created_at timestamp DEFAULT now()
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_monitored_group_listener_group ON monitored_group(listener_instance_id, group_id)",
            "CREATE INDEX IF NOT EXISTS ix_monitored_group_listener ON monitored_group(listener_instance_id)",
            """CREATE TABLE IF NOT EXISTS group_message (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                listener_instance_id varchar(50) NOT NULL,
                group_id varchar(80) NOT NULL,
                group_name varchar(300),
                sender varchar(80),
                sender_name varchar(300),
                id_message varchar(200) NOT NULL UNIQUE,
                type_message varchar(50),
                text text,
                is_voice boolean NOT NULL DEFAULT false,
                audio_url text,
                audio_local_path text,
                transcription text,
                transcription_status varchar(20) NOT NULL DEFAULT 'none',
                transcription_error text,
                matched_keywords text,
                flagged_forbidden boolean NOT NULL DEFAULT false,
                replied boolean NOT NULL DEFAULT false,
                timestamp timestamp,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_group_message_group_created ON group_message(group_id, created_at)",
            """CREATE TABLE IF NOT EXISTS group_keyword (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                word varchar(300) NOT NULL,
                kind varchar(20) NOT NULL DEFAULT 'trigger',
                active boolean NOT NULL DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS group_predefined_reply (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                keyword_id uuid REFERENCES group_keyword(id) ON DELETE CASCADE,
                reply_text text NOT NULL,
                active boolean NOT NULL DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS group_forbidden_alert (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                listener_instance_id varchar(50),
                group_id varchar(80),
                group_name varchar(300),
                sender varchar(80),
                sender_name varchar(300),
                word varchar(300),
                message_text text,
                group_message_id uuid,
                is_read boolean NOT NULL DEFAULT false,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_group_forbidden_alert_created ON group_forbidden_alert(created_at DESC)",
        ]
        for stmt in ddl_v26:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V26] {e}")
        # ── TG — Telegram platform abstraction (additive; WhatsApp defaults preserved) ──
        ddl_tg = [
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS platform varchar(20) NOT NULL DEFAULT 'whatsapp'",
            "ALTER TYPE accountstatus ADD VALUE IF NOT EXISTS 'suspended'",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS api_host varchar(200)",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS authorized_at timestamp",
            "CREATE INDEX IF NOT EXISTS idx_accounts_platform ON accounts(platform)",
            # Telegram group monitoring reuses the V26 tables via a platform column (PART 4).
            "ALTER TABLE monitored_group ADD COLUMN IF NOT EXISTS platform varchar(20) NOT NULL DEFAULT 'whatsapp'",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS platform varchar(20) NOT NULL DEFAULT 'whatsapp'",
            # Telegram warm-up enrollment reuses the V17 table via a platform column (PART 6).
            "ALTER TABLE warmup_enrollment ADD COLUMN IF NOT EXISTS platform varchar(20) NOT NULL DEFAULT 'whatsapp'",
            # Cache the resolved Telegram chatId per (instance, phone) so CheckAccount runs once.
            """CREATE TABLE IF NOT EXISTS telegram_chatid_cache (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                instance_id varchar(50) NOT NULL,
                phone varchar(30) NOT NULL,
                chat_id varchar(60) NOT NULL,
                exist boolean NOT NULL DEFAULT true,
                created_at timestamp DEFAULT now(),
                UNIQUE (instance_id, phone)
            )""",
        ]
        for stmt in ddl_tg:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL TG] {e}")
        # ── V35 PART 3 — contact relationship category + optional referral note on warmup_helper
        #    (both nullable; never break legacy rows). referral_note feeds the AI ask generator. ──
        ddl_v35 = [
            "ALTER TABLE warmup_helper ADD COLUMN IF NOT EXISTS relationship varchar(20)",
            "ALTER TABLE warmup_helper ADD COLUMN IF NOT EXISTS referral_note text",
            # V35 PART 4 — guided onboarding wizard «راه‌اندازی» (SIM → WhatsApp → Green API).
            """CREATE TABLE IF NOT EXISTS account_onboarding (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                phone_number varchar(30) NOT NULL,
                phone_make_model varchar(120),
                sim_inserted_at timestamp,
                whatsapp_activated_at timestamp,
                green_api_login_prompted_at timestamp,
                green_api_connected_at timestamp,
                current_step integer NOT NULL DEFAULT 1,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_account_onboarding_phone ON account_onboarding(phone_number)",
        ]
        for stmt in ddl_v35:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V35] {e}")
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

    # V20 PART 1 — idempotent reconcile: clear stale legacy auto_warmup flags on accounts
    # that have no ACTIVE warm-up enrollment (leaves real enrollments untouched).
    try:
        from app.database import AsyncSessionLocal
        from app.services.warmup_exclusion import reconcile_stale_auto_warmup
        async with AsyncSessionLocal() as db:
            cleared = await reconcile_stale_auto_warmup(db)
            if cleared:
                logger.info("Startup: reconciled %d stale auto_warmup flag(s)", cleared)
    except Exception as e:
        logger.warning("Startup auto_warmup reconcile failed (non-fatal): %s", e)
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
    capabilities_router.router, adlinks.router, warmup.router,
    warmup_helpers.router, group_monitor.router, telegram.router,
    onboarding.router,
]:
    app.include_router(router, prefix="/api/v1")

from app.services.green_api import GreenInstanceDeleted


@app.exception_handler(GreenInstanceDeleted)
async def green_instance_deleted_handler(request: Request, exc: GreenInstanceDeleted):
    """V36 — a Green API call hit an instance the user deleted in the Green API console.
    Return a clean 409 with a Persian message instead of a raw 500, so EVERY endpoint that
    touches such an instance (status/reboot/qr/send/…) degrades gracefully. Endpoints that want
    to also mutate the account row (mark it green_api_deleted) catch it locally first."""
    logger.info("Green API instance gone on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=409, content={
        "detail": "این اینستنس در Green API دیگر وجود ندارد",
        "code": "green_api_deleted",
    })


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
