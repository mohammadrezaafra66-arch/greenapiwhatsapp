"""V67.1 Phase 1 — Fleet 24-hour suspension circuit breaker.

D-C1 Recommended (exact): Coexist then unify to 24h.
Phase 1: fleet breaker (2 distinct accounts suspended in rolling 24h) coexists with
mesh killswitch 48h breaker. Does not weaken or replace the mesh breaker.

Fail-closed: if Redis is unavailable, the breaker is treated as TRIPPED for outbound
automated sends (inbound webhooks / read-only UI remain unaffected by this module).

Manual reset only (owner/ops). Incident history is never deleted on reset.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("afrakala.fleet_breaker")

WINDOW_SECONDS = 24 * 3600
DISTINCT_SUSPEND_THRESHOLD = 2
BREAKER_KEY = "fleet:breaker:v67:tripped"
SUSPEND_MEMBER_PREFIX = "fleet:breaker:v67:suspend:"  # + account_id
SUSPEND_INDEX_KEY = "fleet:breaker:v67:suspend_index"
PAUSE_REASON_FA = "مدار قطع ناوگان — دو تعلیق متمایز در ۲۴ ساعت"


def _member_key(account_id: str) -> str:
    return f"{SUSPEND_MEMBER_PREFIX}{account_id}"


async def _redis():
    from app.services import redis_rate_limiter
    return await redis_rate_limiter.get_redis()


async def record_distinct_suspension(account_id: str, *, now: datetime | None = None,
                                     via: str = "unknown") -> dict[str, Any]:
    """Record a suspension for the rolling 24h window and trip if threshold met.

    Duplicate incidents for the same account within the window refresh TTL but do not
    increase the distinct count. Returns {distinct, tripped, activated_now, reason}.
    Fail-closed on Redis errors: returns tripped=True with reason redis_unavailable.
    """
    now = now or datetime.utcnow()
    aid = str(account_id)
    try:
        r = await _redis()
        pipe = r.pipeline()
        pipe.set(_member_key(aid), now.isoformat(), ex=WINDOW_SECONDS)
        pipe.sadd(SUSPEND_INDEX_KEY, aid)
        pipe.expire(SUSPEND_INDEX_KEY, WINDOW_SECONDS + 60)
        await pipe.execute()
        distinct = await count_distinct_suspensions(now=now)
        out = {
            "distinct": distinct,
            "tripped": False,
            "activated_now": False,
            "reason": None,
            "via": via,
            "account_id": aid,
        }
        if distinct >= DISTINCT_SUSPEND_THRESHOLD:
            activated = await activate_breaker(
                reason="two_distinct_suspensions_24h",
                details={"distinct": distinct, "trigger_account_id": aid, "via": via},
                now=now,
            )
            out["tripped"] = True
            out["activated_now"] = bool(activated.get("activated_now"))
            out["reason"] = "two_distinct_suspensions_24h"
        return out
    except Exception as e:
        logger.error("fleet breaker record_suspension fail-closed: %s", e)
        return {
            "distinct": None,
            "tripped": True,
            "activated_now": False,
            "reason": "redis_unavailable",
            "error": str(e),
            "account_id": aid,
        }


async def count_distinct_suspensions(now: datetime | None = None) -> int:
    """Count account ids that still have a live suspension marker in the 24h window."""
    now = now or datetime.utcnow()
    r = await _redis()
    members = await r.smembers(SUSPEND_INDEX_KEY)
    if not members:
        return 0
    live = 0
    stale = []
    for raw in members:
        aid = raw.decode() if isinstance(raw, bytes) else str(raw)
        if await r.exists(_member_key(aid)):
            live += 1
        else:
            stale.append(aid)
    if stale:
        await r.srem(SUSPEND_INDEX_KEY, *stale)
    return live


async def is_tripped(*, fail_closed: bool = True) -> tuple[bool, str]:
    """Return (tripped, reason). Redis errors → tripped when fail_closed."""
    try:
        r = await _redis()
        raw = await r.get(BREAKER_KEY)
        if not raw:
            return False, "ok"
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            data = json.loads(raw)
            return True, str(data.get("reason") or "tripped")
        except Exception:
            return True, "tripped"
    except Exception as e:
        logger.error("fleet breaker is_tripped fail-closed: %s", e)
        if fail_closed:
            return True, "redis_unavailable"
        return False, "redis_error_fail_open"


async def activate_breaker(reason: str, details: dict | None = None,
                           now: datetime | None = None) -> dict[str, Any]:
    """Idempotent activation. Returns activated_now=False if already tripped."""
    now = now or datetime.utcnow()
    payload = {
        "reason": reason,
        "details": details or {},
        "activated_at": now.isoformat(),
        "manual_reset_only": True,
    }
    try:
        r = await _redis()
        # SET NX so first activation wins; keep payload forever until manual reset.
        created = await r.set(BREAKER_KEY, json.dumps(payload, ensure_ascii=False), nx=True)
        if created:
            logger.critical("FLEET BREAKER ACTIVATED: %s %s", reason, details)
            return {"activated_now": True, "payload": payload}
        existing = await r.get(BREAKER_KEY)
        return {"activated_now": False, "payload": existing}
    except Exception as e:
        logger.error("fleet breaker activate failed: %s", e)
        return {"activated_now": False, "error": str(e), "fail_closed": True}


async def manual_reset(*, reset_by: str = "owner", note: str = "") -> dict[str, Any]:
    """Owner-only reset. Does NOT delete incident history or suspension index evidence
    (index entries expire naturally). Clears only the trip flag."""
    try:
        r = await _redis()
        prev = await r.get(BREAKER_KEY)
        await r.delete(BREAKER_KEY)
        logger.warning("fleet breaker manually reset by=%s note=%s prev=%s",
                       reset_by, note, prev)
        return {"reset": True, "reset_by": reset_by, "previous": prev}
    except Exception as e:
        return {"reset": False, "error": str(e)}


async def status_snapshot() -> dict[str, Any]:
    tripped, reason = await is_tripped()
    try:
        distinct = await count_distinct_suspensions()
    except Exception:
        distinct = None
    return {
        "tripped": tripped,
        "reason": reason,
        "distinct_suspensions_24h": distinct,
        "threshold": DISTINCT_SUSPEND_THRESHOLD,
        "window_seconds": WINDOW_SECONDS,
        "coexists_with_mesh_48h_breaker": True,
        "pause_reason_fa": PAUSE_REASON_FA if tripped else None,
    }
