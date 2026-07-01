from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://afrakala:password@localhost:5432/whatsapp_sender"
    sync_database_url: str = "postgresql://afrakala:password@localhost:5432/whatsapp_sender"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    pricing_cache_minutes: int = 5
    # Supabase REST API — primary source for product names + computed prices.
    supabase_url: str = "https://kwwkppkcihrbeurwudjh.supabase.co"
    supabase_anon_key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt3d2twcGtjaWhyYmV1cnd1ZGpoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwMzU5MTUsImV4cCI6MjA5MjYxMTkxNX0.oowSHbrAEL04u9DwGjyPYIlCc8MSL0c00Odv6UvM4bE"
    secret_key: str = "change-this"
    backend_url: str = "http://localhost:8000"
    webhook_base_url: str = "http://localhost:8000"
    default_min_delay: int = 45
    default_max_delay: int = 110
    debug: bool = True

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
