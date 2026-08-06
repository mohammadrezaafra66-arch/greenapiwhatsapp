"""Phase B delivery adapter tests — sanitized GET, reuses Phase A service."""
from __future__ import annotations
import inspect
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1 import fleet_observation as mod
from app.services.daily_observation.contract import DailyObservationReport


def test_delivery_router_is_get_only_source():
    src = inspect.getsource(mod)
    assert "@router.get" in src
    assert "@router.post" not in src
    assert "@router.put" not in src
    assert "@router.patch" not in src
    assert "@router.delete" not in src
    assert "X-Fleet-Shadow-Token" not in src
    assert "require_shadow_operator" not in src
    assert "DailyObservationReportService" in src


def test_no_green_api_or_send_in_delivery():
    src = inspect.getsource(mod)
    assert "sendMessage" not in src
    assert "GreenAPI" not in src


@pytest.mark.asyncio
async def test_report_endpoint_returns_sanitized_payload():
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/v1")
    fake = {
        "delivery": "v67.owner.daily-observation.delivery.1",
        "read_only": True,
        "report": DailyObservationReport(
            report_date_utc="2026-08-06",
            overall_status="INSUFFICIENT_EVIDENCE",
            phase7_fully_accepted=False,
            phase8_allowed=False,
        ).to_dict(),
        "timeline": [],
    }
    with patch.object(
        mod.DailyObservationReportService,
        "build_owner_payload",
        new=AsyncMock(return_value=fake),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(
                "/api/v1/fleet/observation/report",
                params={"date": "2026-08-06", "include_timeline": False},
            )
    assert r.status_code == 200
    body = r.json()
    assert body["read_only"] is True
    assert body["report"]["phase7_fully_accepted"] is False
    assert body["report"]["phase8_allowed"] is False
    assert "token" not in r.text.lower()


@pytest.mark.asyncio
async def test_invalid_date_400():
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/v1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/fleet/observation/report", params={"date": "bad"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_future_date_400():
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/v1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/fleet/observation/report", params={"date": "2099-01-01"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unsupported_session_400():
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/v1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/api/v1/fleet/observation/report",
            params={"date": "2026-08-06", "session": "session-1"},
        )
    assert r.status_code == 400
