"""V67 Phase 7 — authenticated Shadow operator APIs (D-P7-16)."""
from __future__ import annotations
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.fleet_shadow import FleetShadowSnapshot
from app.services.shadow_auth import require_shadow_operator
from app.services.shadow_runtime import ShadowRuntimeService
from app.services.shadow_types import ShadowRunSource
from app.services import shadow_metrics

router = APIRouter(prefix="/fleet/shadow", tags=["fleet-shadow"])

_SIM_HITS: dict[str, list[float]] = {}
_SIM_LIMIT = 20
_SIM_WINDOW = 60.0


def _rate_limit(request: Request) -> None:
    ip = (request.client.host if request.client else "unknown")
    now = time.time()
    bucket = [t for t in _SIM_HITS.get(ip, []) if now - t < _SIM_WINDOW]
    if len(bucket) >= _SIM_LIMIT:
        raise HTTPException(429, "shadow run-once rate limit exceeded")
    bucket.append(now)
    _SIM_HITS[ip] = bucket


def _public_row(s: FleetShadowSnapshot) -> dict:
    return {
        "id": str(s.id),
        "run_id": str(s.run_id),
        "account_id": str(s.account_id),
        "fleet_account_id": str(s.fleet_account_id),
        "observed_at": s.observed_at.isoformat() if s.observed_at else None,
        "source": s.source,
        "shadow_version": s.shadow_version,
        "policy_version": s.policy_version,
        "mismatch_class": s.mismatch_class,
        "severity": s.severity,
        "eligibility_decision": s.eligibility_decision,
        "legacy_eligibility": s.legacy_eligibility,
        "canonical_fleet_state": s.canonical_fleet_state,
        "dangerous_threshold_status": s.dangerous_threshold_status,
        "reason_codes": s.reason_codes,
        "simulation_only": True,
        "mutates_runtime": False,
        "executes": False,
    }


class ShadowRunOnceBody(BaseModel):
    dry_run: bool = True
    persist: bool = False
    inject_breaker: bool = False
    inject_incident: str | None = None
    inject_stale_sensor: str | None = None
    inject_runtime_unknown: bool = False
    inject_policy_mismatch: bool = False


@router.get("/snapshots")
async def list_snapshots(
    account_id: uuid.UUID | None = None,
    mismatch_class: str | None = None,
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_shadow_operator),
):
    q = select(FleetShadowSnapshot).order_by(FleetShadowSnapshot.observed_at.desc())
    if account_id:
        q = q.where(FleetShadowSnapshot.account_id == account_id)
    if mismatch_class:
        q = q.where(FleetShadowSnapshot.mismatch_class == mismatch_class)
    if severity:
        q = q.where(FleetShadowSnapshot.severity == severity)
    rows = list((await db.execute(q.offset(offset).limit(limit))).scalars().all())
    return {
        "simulation_only": True,
        "mutates_runtime": False,
        "executes": False,
        "count": len(rows),
        "snapshots": [_public_row(r) for r in rows],
    }


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_shadow_operator),
):
    row = (await db.execute(
        select(FleetShadowSnapshot).where(FleetShadowSnapshot.id == snapshot_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "snapshot_not_found")
    out = _public_row(row)
    out["comparison_snapshot"] = row.comparison_snapshot
    out["sensor_freshness"] = row.sensor_freshness
    # never expose tokens
    return out


@router.get("/accounts/{account_id}/latest")
async def account_latest(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_shadow_operator),
):
    row = (await db.execute(
        select(FleetShadowSnapshot)
        .where(FleetShadowSnapshot.account_id == account_id)
        .order_by(FleetShadowSnapshot.observed_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "snapshot_not_found")
    return _public_row(row)


@router.get("/accounts/{account_id}/history")
async def account_history(
    account_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_shadow_operator),
):
    rows = list((await db.execute(
        select(FleetShadowSnapshot)
        .where(FleetShadowSnapshot.account_id == account_id)
        .order_by(FleetShadowSnapshot.observed_at.desc())
        .limit(limit)
    )).scalars().all())
    return {"simulation_only": True, "snapshots": [_public_row(r) for r in rows]}


@router.get("/summary")
async def shadow_summary(
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_shadow_operator),
):
    rows = list((await db.execute(
        select(FleetShadowSnapshot).order_by(FleetShadowSnapshot.observed_at.desc()).limit(500)
    )).scalars().all())
    by_class: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for r in rows:
        by_class[r.mismatch_class] = by_class.get(r.mismatch_class, 0) + 1
        by_sev[r.severity] = by_sev.get(r.severity, 0) + 1
    return {
        "simulation_only": True,
        "mutates_runtime": False,
        "executes": False,
        "dangerous_threshold_status": "UNRATIFIED",
        "sample_size": len(rows),
        "by_mismatch_class": by_class,
        "by_severity": by_sev,
        "metrics": shadow_metrics.snapshot(),
        "feature_flags": {
            "v67_shadow_runtime_enabled": bool(__import__("app.config", fromlist=["settings"]).settings.v67_shadow_runtime_enabled),
            "v67_shadow_scheduler_enabled": bool(__import__("app.config", fromlist=["settings"]).settings.v67_shadow_scheduler_enabled),
        },
    }


@router.get("/drift")
async def shadow_drift(
    severity: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_shadow_operator),
):
    q = select(FleetShadowSnapshot).where(
        FleetShadowSnapshot.mismatch_class != "MATCH"
    ).order_by(FleetShadowSnapshot.observed_at.desc()).limit(limit)
    if severity:
        q = q.where(FleetShadowSnapshot.severity == severity)
    rows = list((await db.execute(q)).scalars().all())
    return {
        "simulation_only": True,
        "dangerous_threshold_status": "UNRATIFIED",
        "drift": [_public_row(r) for r in rows],
    }


@router.get("/status")
async def shadow_status(_auth: dict = Depends(require_shadow_operator)):
    from app.config import settings
    return {
        "simulation_only": True,
        "mutates_runtime": False,
        "executes": False,
        "v67_shadow_runtime_enabled": bool(settings.v67_shadow_runtime_enabled),
        "v67_shadow_scheduler_enabled": bool(settings.v67_shadow_scheduler_enabled),
        "dangerous_threshold_status": "UNRATIFIED",
        "cutover_setter_exists": False,
        "flag_toggle_api_exists": False,
        "metrics": shadow_metrics.snapshot(),
    }


@router.post("/run-once")
async def shadow_run_once(
    request: Request,
    account_id: uuid.UUID,
    body: ShadowRunOnceBody | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_shadow_operator),
):
    _rate_limit(request)
    body = body or ShadowRunOnceBody()
    inject: dict = {}
    if body.inject_breaker:
        inject["breaker"] = True
    if body.inject_incident:
        inject["incident"] = body.inject_incident
    if body.inject_stale_sensor:
        inject["stale_sensor"] = body.inject_stale_sensor
    if body.inject_runtime_unknown:
        inject["runtime_unknown"] = True
    if body.inject_policy_mismatch:
        inject["policy_mismatch"] = True
    result = await ShadowRuntimeService().run_account(
        db, account_id,
        source=ShadowRunSource.API_RUN_ONCE.value,
        persist=bool(body.persist) and not body.dry_run,
        dry_run=body.dry_run,
        inject=inject,
        require_runtime_flag=False,  # manual dry-run allowed while flag false
        use_lock=False,
    )
    if result.get("error") == "account_not_found":
        raise HTTPException(404, result["error"])
    if result.get("error") == "fleet_account_missing":
        raise HTTPException(404, result["error"])
    if result.get("error") == "cutover_true_forbidden":
        raise HTTPException(409, result["error"])
    if body.persist and not body.dry_run and result.get("persisted"):
        await db.commit()
    return result
