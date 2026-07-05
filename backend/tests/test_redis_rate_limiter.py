"""Tests for the Redis-backed rate limiter (A3) — logic verified with a mocked redis."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_redis(day=0, hour=0):
    r = MagicMock()
    # get returns day for the %Y%m%d key, hour for the %Y%m%d%H (longer) key
    async def _get(key):
        return str(hour) if len(key.split(":")[-1]) > 8 else str(day)
    r.get = AsyncMock(side_effect=_get)
    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock()
    r.pipeline = MagicMock(return_value=pipe)
    return r, pipe


@pytest.mark.asyncio
async def test_can_send_true_under_limits():
    from app.services import redis_rate_limiter as rl
    r, _ = _mock_redis(day=3, hour=1)
    with patch.object(rl, "get_redis", new=AsyncMock(return_value=r)):
        ok, reason = await rl.can_send("acc", daily_limit=200, hourly_limit=50)
    assert ok is True and reason == "ok"


@pytest.mark.asyncio
async def test_can_send_false_daily_cap():
    from app.services import redis_rate_limiter as rl
    r, _ = _mock_redis(day=200, hour=0)
    with patch.object(rl, "get_redis", new=AsyncMock(return_value=r)):
        ok, reason = await rl.can_send("acc", daily_limit=200, hourly_limit=50)
    assert ok is False and "روزانه" in reason


@pytest.mark.asyncio
async def test_can_send_false_hourly_cap():
    from app.services import redis_rate_limiter as rl
    r, _ = _mock_redis(day=5, hour=50)
    with patch.object(rl, "get_redis", new=AsyncMock(return_value=r)):
        ok, reason = await rl.can_send("acc", daily_limit=200, hourly_limit=50)
    assert ok is False and "ساعتی" in reason


@pytest.mark.asyncio
async def test_record_send_increments_both_counters_with_ttl():
    from app.services import redis_rate_limiter as rl
    r, pipe = _mock_redis()
    with patch.object(rl, "get_redis", new=AsyncMock(return_value=r)):
        await rl.record_send("acc")
    assert pipe.incr.call_count == 2      # day + hour
    assert pipe.expire.call_count == 2    # TTL on each
    pipe.execute.assert_awaited_once()
