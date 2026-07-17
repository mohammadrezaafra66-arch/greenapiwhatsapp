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


def delay_for_platform(platform: str | None, wa_delay: tuple[int, int]) -> tuple[int, int]:
    """TG — return the send delay for `platform`. Telegram uses its OWN 10–15s pacing
    constant (never the WhatsApp delay); any other platform keeps `wa_delay` unchanged."""
    from app.services.platforms import normalize_platform, telegram_delay_seconds
    if normalize_platform(platform) == "telegram":
        return telegram_delay_seconds()
    return wa_delay


async def get_delay_for_account(account) -> tuple[int, int]:
    """Platform-aware (min, max) send delay for an Account row. WhatsApp keeps its per-account
    config; Telegram is forced onto its distinct 10–15s constant."""
    wa = await get_delay(str(account.id))
    return delay_for_platform(getattr(account, "platform", "whatsapp"), wa)


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
