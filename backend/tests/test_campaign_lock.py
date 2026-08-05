"""Tests for the campaign single-run lock (B1.3/B1.4 safety primitive).

The lock is what makes startup-resume and orphan-recovery safe: a re-queue for a
campaign that is already running must NOT double-send.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_run_campaign_fail_closed_when_redis_down():
    """V67 Phase 1 — Redis unavailable must NOT run the campaign (fail-closed)."""
    from app.services import campaign_runner
    inner = AsyncMock()
    inst = MagicMock()
    inst.acquire = AsyncMock(return_value=False)
    inst.fail_closed_reason = "قفل کمپین — Redis در دسترس نیست (شکست‌بسته)"
    inst.skip_reason = inst.fail_closed_reason
    inst.release = AsyncMock()
    with patch("app.services.campaign_lock.CampaignLock", return_value=inst), \
         patch.object(campaign_runner, "_run_campaign_inner", new=inner), \
         patch.object(campaign_runner, "_pause_campaign_for_safety", new=AsyncMock()), \
         patch("app.services.fleet_breaker.is_tripped", new=AsyncMock(return_value=(False, "ok"))):
        await campaign_runner.run_campaign("cid")
    inner.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_campaign_skips_when_lock_held():
    from app.services import campaign_runner
    inner = AsyncMock()
    inst = MagicMock()
    inst.acquire = AsyncMock(return_value=False)
    inst.fail_closed_reason = None
    inst.skip_reason = "held"
    inst.release = AsyncMock()
    with patch("app.services.campaign_lock.CampaignLock", return_value=inst), \
         patch.object(campaign_runner, "_run_campaign_inner", new=inner), \
         patch("app.services.fleet_breaker.is_tripped", new=AsyncMock(return_value=(False, "ok"))):
        await campaign_runner.run_campaign("cid")
    inner.assert_not_awaited()
    inst.release.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_campaign_runs_and_releases_lock_when_acquired():
    from app.services import campaign_runner
    inner = AsyncMock()
    inst = MagicMock()
    inst.acquire = AsyncMock(return_value=True)
    inst.fail_closed_reason = None
    inst.token = "tok"
    inst.release = AsyncMock()
    with patch("app.services.campaign_lock.CampaignLock", return_value=inst), \
         patch.object(campaign_runner, "_run_campaign_inner", new=inner), \
         patch("app.services.fleet_breaker.is_tripped", new=AsyncMock(return_value=(False, "ok"))):
        await campaign_runner.run_campaign("cid")
    inner.assert_awaited_once()
    inst.release.assert_awaited_once()
