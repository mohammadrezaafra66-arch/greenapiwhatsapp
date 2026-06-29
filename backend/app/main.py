from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.api.v1 import accounts, campaigns, contacts, webhook, dashboard, blacklist

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="Afrakala WhatsApp Sender",
    description="واتس‌اپ سندر حرفه‌ای افراکالا با Green API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(campaigns.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")
app.include_router(webhook.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(blacklist.router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Afrakala WhatsApp Sender"}
