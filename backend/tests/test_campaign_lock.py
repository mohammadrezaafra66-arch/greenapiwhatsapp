"""Tests for the campaign single-run lock (B1.3/B1.4 safety primitive).

The lock is what makes startup-resume and orphan-recovery safe: a re-queue for a
campaign that is already running must NOT double-send.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_run_campaign_skips_when_lock_held():
    from app.services import campaign_runner
    r = MagicMock()
    r.set = AsyncMock(return_value=False)   # NX failed → another run holds it
    r.delete = AsyncMock()
    inner = AsyncMock()
    with patch("app.services.redis_rate_limiter.get_redis", new=AsyncMock(return_value=r)), \
         patch.object(campaign_runner, "_run_campaign_inner", new=inner):
        await campaign_runner.run_campaign("cid")
    inner.assert_not_awaited()   # duplicate run was skipped
    r.delete.assert_not_awaited()  # must not release a lock it didn't take


@pytest.mark.asyncio
async def test_run_campaign_runs_and_releases_lock_when_acquired():
    from app.services import campaign_runner
    r = MagicMock()
    r.set = AsyncMock(return_value=True)    # acquired
    r.delete = AsyncMock()
    inner = AsyncMock()
    with patch("app.services.redis_rate_limiter.get_redis", new=AsyncMock(return_value=r)), \
         patch.object(campaign_runner, "_run_campaign_inner", new=inner):
        await campaign_runner.run_campaign("cid")
    inner.assert_awaited_once()
    r.delete.assert_awaited_once()   # lock released in finally


@pytest.mark.asyncio
async def test_run_campaign_fail_open_when_redis_down():
    from app.services import campaign_runner
    inner = AsyncMock()
    with patch("app.services.redis_rate_limiter.get_redis", new=AsyncMock(side_effect=Exception("redis down"))), \
         patch.object(campaign_runner, "_run_campaign_inner", new=inner):
        await campaign_runner.run_campaign("cid")
    inner.assert_awaited_once()   # Redis unavailable → still runs (fail-open)
