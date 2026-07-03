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
]:
    app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
