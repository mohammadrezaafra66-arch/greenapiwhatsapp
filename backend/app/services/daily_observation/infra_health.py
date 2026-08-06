"""Minimal read-only infrastructure probes (reuse existing Redis/Celery/DB patterns)."""
from __future__ import annotations
from typing import Any

from app.services.daily_observation.contract import InfraStatus


async def probe_database(db_session_factory) -> str:
    try:
        from sqlalchemy import text

        async with db_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return InfraStatus.HEALTHY.value
    except Exception:
        return InfraStatus.UNHEALTHY.value


async def probe_redis() -> str:
    try:
        from app.services import redis_rate_limiter

        r = await redis_rate_limiter.get_redis()
        await r.ping()
        return InfraStatus.HEALTHY.value
    except Exception:
        return InfraStatus.UNHEALTHY.value


def probe_celery_workers(timeout: float = 1.0) -> str:
    try:
        from app.workers.celery_app import celery_app

        pong = celery_app.control.ping(timeout=timeout)
        workers = [list(w.keys())[0] for w in pong] if pong else []
        if workers:
            return InfraStatus.HEALTHY.value
        return InfraStatus.UNHEALTHY.value
    except Exception:
        return InfraStatus.UNHEALTHY.value


def read_shadow_flags() -> dict[str, Any]:
    from app.config import settings

    return {
        "runtime_enabled": bool(settings.v67_shadow_runtime_enabled),
        "scheduler_enabled": bool(settings.v67_shadow_scheduler_enabled),
        "runtime_status": (
            InfraStatus.HEALTHY.value
            if settings.v67_shadow_runtime_enabled
            else InfraStatus.UNHEALTHY.value
        ),
        "scheduler_flag_status": (
            InfraStatus.HEALTHY.value
            if settings.v67_shadow_scheduler_enabled
            else InfraStatus.UNHEALTHY.value
        ),
    }


def derive_scheduler_status(
    *,
    scheduler_flag: bool,
    last_periodic_at,
    now,
    max_age_seconds: int,
) -> str:
    """Flag alone is insufficient — require recent periodic snapshot when flag true."""
    if not scheduler_flag:
        return InfraStatus.UNHEALTHY.value
    if last_periodic_at is None:
        return InfraStatus.DEGRADED.value
    age = (now - last_periodic_at).total_seconds()
    if age > max_age_seconds:
        return InfraStatus.DEGRADED.value
    return InfraStatus.HEALTHY.value


def derive_scheduler_status_historical(*, scheduler_flag: bool, had_periodic: bool) -> str:
    """Day-scoped scheduler evidence for past UTC days (no live-age hybrid)."""
    if not scheduler_flag:
        return InfraStatus.UNHEALTHY.value
    if had_periodic:
        return InfraStatus.HEALTHY.value
    return InfraStatus.DEGRADED.value


def derive_beat_status(*, last_periodic_at, scheduler_flag: bool) -> str:
    """No dedicated Beat health API — infer cautiously or UNKNOWN."""
    if last_periodic_at is not None and scheduler_flag:
        return InfraStatus.HEALTHY.value
    if scheduler_flag and last_periodic_at is None:
        return InfraStatus.UNKNOWN.value
    return InfraStatus.UNKNOWN.value
