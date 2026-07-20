from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://afrakala:password@localhost:5432/whatsapp_sender"
    sync_database_url: str = "postgresql://afrakala:password@localhost:5432/whatsapp_sender"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    pricing_cache_minutes: int = 5
    # V16 PART 4 — send-path price cache TTL (seconds). Short so a mid-campaign price
    # change is reflected within a minute (per-message fetch + ≤60s cache).
    price_cache_seconds: int = 60
    # Supabase REST API — primary source for product names + computed prices.
    # Self-hosted Supabase (Kong gateway) on the local network.
    # NOTE: the anon key is a secret — set SUPABASE_ANON_KEY in .env (not committed).
    supabase_url: str = "http://192.168.170.10:8000"
    supabase_anon_key: str = ""
    secret_key: str = "change-this"
    backend_url: str = "http://localhost:8000"
    webhook_base_url: str = "http://localhost:8000"
    default_min_delay: int = 45
    default_max_delay: int = 110
    debug: bool = True
    # V14 — Green API Partner. Token is a SECRET (never logged/returned). When empty,
    # every Partner UI element renders but is disabled (see api/v1/partner.py).
    green_partner_token: str = ""
    green_partner_api_url: str = "https://api.green-api.com"
    partner_daily_rate: float = 0
    # TG — Telegram is a SEPARATE Green API partner project ("4500 Telegram") with its OWN
    # partner key + API base, stored DISTINCTLY from the WhatsApp partner credentials above.
    # Never let a Telegram call use the WhatsApp key or vice-versa (see services/platforms.py).
    green_partner_token_telegram: str = ""
    green_partner_api_url_telegram: str = "https://api.green-api.com"
    # TG — Telegram-specific pacing/limits (NEVER share the WhatsApp delay constants).
    telegram_min_delay_seconds: int = 10
    telegram_max_delay_seconds: int = 15
    # V14 F23.4 — semi-automatic failover after yellowCard (default OFF: silently moving
    # load to another number can card it too if the message content is the trigger).
    auto_failover_on_yellow_card: bool = False
    # When true (Celery worker/beat), use NullPool — each task runs on a fresh
    # event loop via asyncio.run and pooled asyncpg conns can't cross loops.
    # When false (API), use a real connection pool for concurrency.
    worker_mode: bool = False
    # Read-only public reports API (/api/v1/reports/*) — comma-separated CORS allowlist for the
    # LAN system that renders the top-products tab. Set REPORTS_ALLOWED_ORIGINS in .env to add the
    # new machine when it moves (e.g. "http://192.168.170.10:3100") — no code change needed. Use
    # "*" to allow any origin. This allowlist applies ONLY to /api/v1/reports/* (see main.py); the
    # rest of the API keeps its own CORS untouched.
    reports_allowed_origins: str = "http://192.168.170.8:3100,http://192.168.170.10:3100"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
