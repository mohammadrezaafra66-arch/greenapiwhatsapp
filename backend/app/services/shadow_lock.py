"""V67 Phase 7 — per-account Shadow Redis lock (fail-closed for periodic)."""
from __future__ import annotations
import logging
import secrets
import uuid

logger = logging.getLogger("afrakala.shadow_lock")


class ShadowAccountLock:
    def __init__(self, account_id: str, *, ttl: int = 60):
        self.account_id = str(account_id)
        self.ttl = int(ttl)
        self.key = f"fleet:shadow:lock:{self.account_id}"
        self.token = f"{uuid.uuid4().hex}:{secrets.token_hex(8)}"
        self.acquired = False
        self.fail_closed_reason: str | None = None
        self._r = None

    async def acquire(self) -> bool:
        try:
            from app.services import redis_rate_limiter
            self._r = await redis_rate_limiter.get_redis()
            ok = await self._r.set(self.key, self.token, nx=True, ex=self.ttl)
            self.acquired = bool(ok)
            return self.acquired
        except Exception as e:
            logger.error("shadow lock fail-closed for %s: %s", self.account_id, e)
            self.fail_closed_reason = "redis_unavailable"
            self.acquired = False
            return False

    async def release(self) -> None:
        if not self.acquired or self._r is None:
            return
        try:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
              return redis.call('del', KEYS[1])
            end
            return 0
            """
            await self._r.eval(script, 1, self.key, self.token)
        except Exception as e:
            logger.warning("shadow lock release error: %s", e)
        finally:
            self.acquired = False
