"""V67.1 Phase 1 — Campaign Redis lock (fail-closed).

Phase 1 Acceptance + D-C3 note: campaign lock is fail-closed now (executes the
“then closed” clause of D-C3 Recommended for the campaign path). AFM action-claim
locks remain Phase 5.

Semantics:
- Redis unavailable → do not run (fail-closed)
- Lock held by another owner → skip
- Ownership token required for release
- TTL 4h with optional heartbeat renewal
- Wrong owner cannot release
"""
from __future__ import annotations
import logging
import secrets
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger("afrakala.campaign_lock")

LOCK_TTL_SECONDS = 14400  # 4h
LOCK_PREFIX = "campaign_lock:"
PAUSE_REASON_REDIS = "قفل کمپین — Redis در دسترس نیست (شکست‌بسته)"
PAUSE_REASON_HELD = "کمپین در حال اجراست (قفل فعال)"


def lock_key(campaign_id: str) -> str:
    return f"{LOCK_PREFIX}{campaign_id}"


def new_owner_token() -> str:
    return f"{uuid.uuid4().hex}:{secrets.token_hex(8)}"


class CampaignLock:
    """Holds ownership of a campaign run. Use as async context or acquire/release."""

    def __init__(self, campaign_id: str, *, ttl: int = LOCK_TTL_SECONDS):
        self.campaign_id = str(campaign_id)
        self.ttl = int(ttl)
        self.key = lock_key(self.campaign_id)
        self.token = new_owner_token()
        self.acquired = False
        self._r = None
        self.skip_reason: str | None = None
        self.fail_closed_reason: str | None = None

    async def acquire(self) -> bool:
        """True if this worker owns the lock. False = skip (held). Raises/sets fail_closed on Redis error."""
        try:
            from app.services import redis_rate_limiter
            self._r = await redis_rate_limiter.get_redis()
            ok = await self._r.set(self.key, self.token, nx=True, ex=self.ttl)
            if ok:
                self.acquired = True
                self.skip_reason = None
                self.fail_closed_reason = None
                return True
            self.acquired = False
            self.skip_reason = PAUSE_REASON_HELD
            return False
        except Exception as e:
            logger.error("campaign lock acquire fail-closed for %s: %s", self.campaign_id, e)
            self.acquired = False
            self.fail_closed_reason = PAUSE_REASON_REDIS
            self.skip_reason = PAUSE_REASON_REDIS
            self._r = None
            return False

    async def heartbeat(self) -> bool:
        """Renew TTL only if we still own the lock."""
        if not self.acquired or self._r is None:
            return False
        try:
            # Lua: renew only if value matches token
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
              return redis.call('expire', KEYS[1], ARGV[2])
            else
              return 0
            end
            """
            res = await self._r.eval(script, 1, self.key, self.token, str(self.ttl))
            return bool(res)
        except Exception as e:
            logger.warning("campaign lock heartbeat failed for %s: %s", self.campaign_id, e)
            return False

    async def release(self) -> bool:
        """Owner-only release. Wrong token → no-op False."""
        if self._r is None:
            return False
        try:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
              return redis.call('del', KEYS[1])
            else
              return 0
            end
            """
            res = await self._r.eval(script, 1, self.key, self.token)
            released = bool(res)
            if released:
                self.acquired = False
            return released
        except Exception as e:
            logger.warning("campaign lock release failed for %s: %s", self.campaign_id, e)
            return False

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.acquired:
            await self.release()
        return False


async def force_release_if_owner(campaign_id: str, token: str) -> bool:
    """Test/ops helper: release only with matching ownership token."""
    lock = CampaignLock(campaign_id)
    lock.token = token
    try:
        from app.services import redis_rate_limiter
        lock._r = await redis_rate_limiter.get_redis()
        return await lock.release()
    except Exception:
        return False


def lock_audit_event(campaign_id: str, action: str, **extra) -> dict[str, Any]:
    return {
        "campaign_id": str(campaign_id),
        "action": action,
        "at": datetime.utcnow().isoformat(),
        **extra,
    }
