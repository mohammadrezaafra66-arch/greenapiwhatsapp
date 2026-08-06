"""Owner Change Phase B — sanitized read-only Daily Observation delivery adapter.

Reuses DailyObservationReportService. No Shadow operator token. No writes.
Not a Control Plane. Not Master Phase 11.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.services.daily_observation.service import DailyObservationReportService
from app.services.daily_observation.session_meta import (
    EXPECTED_TOTAL_DAYS,
    SESSION_2_ID,
    SESSION_2_STARTED_AT_UTC,
)

router = APIRouter(prefix="/fleet/observation", tags=["fleet-observation-owner"])


def _validate_owner_date(day: str) -> None:
    try:
        d = datetime.strptime(day, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid_date") from e
    day0 = datetime(
        SESSION_2_STARTED_AT_UTC.year,
        SESSION_2_STARTED_AT_UTC.month,
        SESSION_2_STARTED_AT_UTC.day,
    )
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    max_day = day0 + timedelta(days=EXPECTED_TOTAL_DAYS)
    if d.date() > today.date():
        raise HTTPException(status_code=400, detail="future_date_not_allowed")
    # Allow before session (service returns NOT_APPLICABLE) but bound far history
    if d < day0 - timedelta(days=1):
        raise HTTPException(status_code=400, detail="date_out_of_bounds")
    if d > max_day + timedelta(days=1):
        raise HTTPException(status_code=400, detail="date_out_of_bounds")


@router.get("/report")
async def owner_daily_observation_report(
    date: str = Query(..., description="UTC YYYY-MM-DD"),
    session: str = Query(SESSION_2_ID),
    include_timeline: bool = Query(True),
):
    """Sanitized GET for owner UI. No token. Read-only. Bounded date."""
    if session != SESSION_2_ID:
        raise HTTPException(status_code=400, detail="unsupported_session")
    _validate_owner_date(date)
    try:
        payload = await DailyObservationReportService().build_owner_payload(
            date, include_timeline=include_timeline
        )
    except ValueError as e:
        if str(e).startswith("invalid_date"):
            raise HTTPException(status_code=400, detail="invalid_date") from e
        raise HTTPException(status_code=400, detail="bad_request") from e
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="report_unavailable",
        ) from None
    return payload
