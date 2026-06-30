from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database import engine, Base
import app.models  # noqa: F401  (register all models on Base.metadata)
from app.api.v1 import (
    accounts, campaigns, contacts, webhook, dashboard,
    inbox, groups, statuses, templates, queue, blacklist,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS polling_enabled boolean DEFAULT false"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS is_deleted boolean DEFAULT false"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS edited_text text"))
        await conn.execute(text("ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS original_message_id varchar(200)"))
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
]:
    app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
