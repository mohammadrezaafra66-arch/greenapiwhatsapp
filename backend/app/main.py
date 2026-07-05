from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database import engine, Base
import app.models  # noqa: F401  (register all models on Base.metadata)
from app.api.v1 import (
    accounts, campaigns, contacts, webhook, dashboard,
    inbox, groups, statuses, templates, queue, blacklist,
    keyword_rules, account_schedules,
    journals, files as files_router,
    contact_groups, wa_collections, reporting as reporting_router,
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
    # Startup config sanity checks
    from app.config import settings as _settings
    if not _settings.supabase_anon_key:
        print("[WARN] SUPABASE_ANON_KEY is empty — set it in .env; product prices will be unavailable.")
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
]:
    app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
