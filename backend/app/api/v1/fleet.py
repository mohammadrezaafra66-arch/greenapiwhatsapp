"""V67 Phase 2 — read-only fleet API (no Autopilot / journey mutation)."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import fleet_service, fleet_seed

router = APIRouter(prefix="/fleet", tags=["fleet"])


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
