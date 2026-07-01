"""
Get the send delay (min, max seconds) for a given account.
Falls back to env-configured defaults if no per-account config exists.
"""
from app.database import AsyncSessionLocal
from app.models.account_send_config import AccountSendConfig
from app.config import settings
import uuid


async def get_delay(account_id: str) -> tuple[int, int]:
    """Returns (min_seconds, max_seconds) for this account."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AccountSendConfig).where(
                AccountSendConfig.account_id == uuid.UUID(account_id)
            )
        )
        config = result.scalar_one_or_none()
        if config:
            return config.min_delay_seconds, config.max_delay_seconds
    return settings.default_min_delay, settings.default_max_delay


async def set_delay(account_id: str, min_sec: int, max_sec: int):
    """Upsert the per-account send delay config."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AccountSendConfig).where(
                AccountSendConfig.account_id == uuid.UUID(account_id)
            )
        )
        config = result.scalar_one_or_none()
        if config:
            config.min_delay_seconds = min_sec
            config.max_delay_seconds = max_sec
        else:
            db.add(AccountSendConfig(
                account_id=uuid.UUID(account_id),
                min_delay_seconds=min_sec,
                max_delay_seconds=max_sec,
            ))
        await db.commit()
