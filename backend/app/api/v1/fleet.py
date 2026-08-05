"""V67 Phase 2/3 — fleet API: read-only + simulation (no live journey / cutover)."""
from __future__ import annotations
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account_journey import AccountJourney
from app.services import fleet_service, fleet_seed
from app.services.journey_orchestrator import JourneyOrchestrator
from app.services.journey_types import JourneyType

router = APIRouter(prefix="/fleet", tags=["fleet"])

# Soft in-process rate limit for simulate (best-effort; no Redis dependency).
_SIM_HITS: dict[str, list[float]] = {}
_SIM_LIMIT = 30
_SIM_WINDOW = 60.0


def _rate_limit_simulate(request: Request) -> None:
    ip = (request.client.host if request.client else "unknown")
    now = time.time()
    bucket = [t for t in _SIM_HITS.get(ip, []) if now - t < _SIM_WINDOW]
    if len(bucket) >= _SIM_LIMIT:
        raise HTTPException(429, "simulate rate limit exceeded")
    bucket.append(now)
    _SIM_HITS[ip] = bucket


@router.get("/accounts")
async def list_fleet_accounts(limit: int = Query(100, ge=1, le=500),
                              db: AsyncSession = Depends(get_db)):
    rows = await fleet_service.list_fleet_accounts(db, limit=limit)
    return [{
        "id": str(r.id),
        "account_id": str(r.account_id),
        "fleet_state": r.fleet_state,
        "risk_budget": r.risk_budget,
        "cutover": r.cutover,
        "state_reason": r.state_reason,
        "version": r.version,
        "state_changed_at": r.state_changed_at.isoformat() if r.state_changed_at else None,
    } for r in rows]


@router.get("/accounts/{account_id}")
async def get_fleet_account(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await fleet_service.get_fleet_account(db, account_id)
    if row is None:
        raise HTTPException(404, "fleet account not found")
    return {
        "id": str(row.id),
        "account_id": str(row.account_id),
        "fleet_state": row.fleet_state,
        "journey_type": row.journey_type,
        "policy_id": str(row.policy_id) if row.policy_id else None,
        "risk_budget": row.risk_budget,
        "cutover": row.cutover,
        "state_reason": row.state_reason,
        "paused_reason": row.paused_reason,
        "version": row.version,
        "state_changed_at": row.state_changed_at.isoformat() if row.state_changed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/accounts/{account_id}/diagnostics")
async def fleet_diagnostics(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await fleet_service.sensor_mismatch_diagnostics(db, account_id)


@router.get("/policies/default")
async def get_default_policy(db: AsyncSession = Depends(get_db)):
    row = await fleet_service.get_default_policy(db)
    if row is None:
        raise HTTPException(404, "no default fleet policy")
    return {
        "id": str(row.id),
        "name": row.name,
        "version": row.version,
        "policy_type": row.policy_type,
        "is_active": row.is_active,
        "is_default": row.is_default,
        "settings_json": row.settings_json,
    }


@router.post("/seed/preview")
async def seed_preview(
    account_id: uuid.UUID | None = None,
    batch_size: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run seed plan only — never applies."""
    plans = await fleet_seed.build_seed_plan(db, account_id=account_id, batch_size=batch_size)
    return {"dry_run": True, "count": len(plans), "plans": fleet_seed.plans_as_dicts(plans)}


# ── Phase 3 journey read / simulate ─────────────────────────────────────────

@router.get("/journeys")
async def list_journeys(limit: int = Query(100, ge=1, le=500),
                        db: AsyncSession = Depends(get_db)):
    rows = list((await db.execute(
        select(AccountJourney).order_by(AccountJourney.updated_at.desc()).limit(limit)
    )).scalars().all())
    return [{
        "id": str(j.id),
        "account_id": str(j.account_id),
        "fleet_account_id": str(j.fleet_account_id),
        "journey_type": j.journey_type,
        "status": j.status,
        "current_state": j.current_state,
        "simulation_only": j.simulation_only,
        "shadow_mode": j.shadow_mode,
        "version": j.version,
    } for j in rows]


@router.get("/journeys/{journey_id}")
async def get_journey(journey_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    j = (await db.execute(
        select(AccountJourney).where(AccountJourney.id == journey_id)
    )).scalar_one_or_none()
    if j is None:
        raise HTTPException(404, "journey not found")
    return {
        "id": str(j.id),
        "account_id": str(j.account_id),
        "fleet_account_id": str(j.fleet_account_id),
        "journey_type": j.journey_type,
        "status": j.status,
        "current_state": j.current_state,
        "policy_snapshot": j.policy_snapshot,
        "evidence_snapshot": j.evidence_snapshot,
        "simulation_only": j.simulation_only,
        "shadow_mode": j.shadow_mode,
        "version": j.version,
        "started_at": j.started_at.isoformat() if j.started_at else None,
    }


@router.get("/accounts/{account_id}/journey-preview")
async def journey_preview(
    account_id: uuid.UUID,
    journey_type: str = Query(JourneyType.NEW_ACCOUNT.value),
    db: AsyncSession = Depends(get_db),
):
    return await JourneyOrchestrator().preview(db, account_id, journey_type=journey_type)


@router.get("/accounts/{account_id}/shadow-comparison")
async def shadow_comparison(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    preview = await JourneyOrchestrator().preview(db, account_id)
    if preview.get("error"):
        raise HTTPException(404, preview["error"])
    return preview.get("shadow", {})


class SimulateBody(BaseModel):
    journey_type: str = JourneyType.NEW_ACCOUNT.value
    persist_simulation: bool = False
    inject_suspended: bool = False
    inject_blocked: bool = False
    inject_forced_logout: bool = False
    inject_breaker: bool = False
    inject_webhook_stale: bool = False
    days: int | None = None
    elapsed_hours: float | None = None


@router.post("/accounts/{account_id}/simulate-journey")
async def simulate_journey(
    account_id: uuid.UUID,
    request: Request,
    body: SimulateBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Simulation only. Default dry-run. Never enables cutover or live sends."""
    _rate_limit_simulate(request)
    body = body or SimulateBody()
    inject = {
        "suspended": body.inject_suspended,
        "blocked": body.inject_blocked,
        "forced_logout": body.inject_forced_logout,
        "breaker": body.inject_breaker,
        "webhook_stale": body.inject_webhook_stale,
    }
    if body.days is not None:
        inject["days"] = body.days
    if body.elapsed_hours is not None:
        inject["elapsed_hours"] = body.elapsed_hours
    result = await JourneyOrchestrator().simulate_and_maybe_persist(
        db,
        account_id,
        journey_type=body.journey_type,
        persist_simulation=body.persist_simulation,
        inject=inject,
    )
    if result.get("error") == "account_not_found":
        raise HTTPException(404, result["error"])
    if body.persist_simulation and result.get("persisted"):
        await db.commit()
    result.pop("api_token", None)
    result.pop("token", None)
    return result


# ── Phase 4 trust / risk / graduation simulation ─────────────────────────────

class ScoreSimulateBody(BaseModel):
    persist: bool = False
    inject_suspended: bool = False
    inject_blocked: bool = False
    inject_inactivity: bool = False
    inject_webhook_failure: bool = False
    inject_breaker: bool = False
    inactivity_days: int | None = None


@router.post("/accounts/{account_id}/simulate-scores")
async def simulate_scores(
    account_id: uuid.UUID,
    request: Request,
    body: ScoreSimulateBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Phase 4: simulate trust/risk/readiness. Never mutates FleetState or send_gate."""
    from app.services.fleet_scoring import FleetScoringService
    _rate_limit_simulate(request)
    body = body or ScoreSimulateBody()
    inject = {
        "suspended": body.inject_suspended,
        "blocked": body.inject_blocked,
        "inactivity": body.inject_inactivity,
        "webhook_failure": body.inject_webhook_failure,
        "breaker": body.inject_breaker,
    }
    if body.inactivity_days is not None:
        inject["inactivity_days"] = body.inactivity_days
    result = await FleetScoringService().simulate(
        db, account_id, inject=inject, persist=body.persist,
    )
    if result.get("error") == "account_not_found":
        raise HTTPException(404, result["error"])
    if body.persist and result.get("persisted"):
        await db.commit()
    return result


@router.get("/accounts/{account_id}/trust")
async def get_trust_preview(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.services.fleet_scoring import FleetScoringService
    result = await FleetScoringService().simulate(db, account_id, persist=False)
    if result.get("error"):
        raise HTTPException(404, result["error"])
    return result["trust"]


@router.get("/accounts/{account_id}/risk")
async def get_risk_preview(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.services.fleet_scoring import FleetScoringService
    result = await FleetScoringService().simulate(db, account_id, persist=False)
    if result.get("error"):
        raise HTTPException(404, result["error"])
    return result["risk"]


@router.get("/accounts/{account_id}/graduation-preview")
async def graduation_preview(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.services.fleet_scoring import FleetScoringService
    result = await FleetScoringService().simulate(db, account_id, persist=False)
    if result.get("error"):
        raise HTTPException(404, result["error"])
    return {
        "graduation_trial": result["graduation_trial"],
        "readiness": result["readiness"],
        "canonical_fleet_state": result["canonical_fleet_state"],
        "fleet_state_mutated": False,
        "simulation_only": True,
    }


# ── Phase 5 capacity / campaign planning (simulation only) ───────────────────

class CampaignPlanBody(BaseModel):
    target_messages: int = 100
    batch_size: int = 10
    spacing_minutes: int = 20
    persist: bool = False


@router.get("/capacity")
async def fleet_capacity(
    account_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.fleet_planning import FleetPlanningService
    return await FleetPlanningService().capacity_preview(db, account_id=account_id)


@router.get("/budget")
async def fleet_budget(db: AsyncSession = Depends(get_db)):
    from app.services.fleet_planning import FleetPlanningService
    preview = await FleetPlanningService().capacity_preview(db)
    return {
        "simulation_only": True,
        "budgets": [p["budget"] for p in preview.get("plans", [])],
        "mutates_runtime": False,
    }


@router.get("/planner")
async def fleet_planner(db: AsyncSession = Depends(get_db)):
    from app.services.fleet_planning import FleetPlanningService
    return await FleetPlanningService().campaign_plan_simulate(db, persist=False)


@router.get("/schedule-preview")
async def schedule_preview(account_id: str | None = None, db: AsyncSession = Depends(get_db)):
    from app.services.fleet_planning import FleetPlanningService
    return await FleetPlanningService().schedule_preview(db, account_id=account_id)


@router.post("/simulate-capacity")
async def simulate_capacity(
    request: Request,
    account_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.fleet_planning import FleetPlanningService
    _rate_limit_simulate(request)
    out = await FleetPlanningService().capacity_preview(db, account_id=account_id)
    out["dry_run"] = True
    return out


@router.post("/simulate-campaign-plan")
async def simulate_campaign_plan(
    request: Request,
    body: CampaignPlanBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.fleet_planning import FleetPlanningService
    _rate_limit_simulate(request)
    body = body or CampaignPlanBody()
    result = await FleetPlanningService().campaign_plan_simulate(
        db,
        campaign={
            "target_messages": body.target_messages,
            "batch_size": body.batch_size,
            "spacing_minutes": body.spacing_minutes,
        },
        persist=body.persist,
    )
    if body.persist and result.get("persisted"):
        await db.commit()
    return result
