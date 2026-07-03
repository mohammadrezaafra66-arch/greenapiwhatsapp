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
    # Supabase REST API — primary source for product names + computed prices.
    # Self-hosted Supabase (Kong gateway) on the local network.
    supabase_url: str = "http://192.168.170.10:8000"
    supabase_anon_key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzc5MDA1NjkxLCJleHAiOjIwOTQzNjU2OTF9.0LMk6WGniEm92wPtTnapSIcuhZpq5au8KnEUCQFPKeI"
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
