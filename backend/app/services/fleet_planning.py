"""V67 Phase 5 — planning facade (DB read + pure planners; dry-run default)."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.fleet_account import FleetAccount
from app.models.fleet_policy import FleetPolicy
from app.models.fleet_plan import FleetPlanSnapshot
from app.services.capacity_planner import CapacityPlanner
from app.services.fleet_budget import FleetBudgetEngine
from app.services.campaign_planner import CampaignPlanner
from app.services.schedule_planner import SchedulePlanner
from app.services.fleet_optimizer import FleetOptimizer
from app.services.trust_engine import TrustEngine
from app.services.risk_engine import RiskEngine
from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS


class FleetPlanningService:
    def __init__(self):
        self.capacity = CapacityPlanner()
        self.budget = FleetBudgetEngine()
        self.campaign = CampaignPlanner()
        self.schedule = SchedulePlanner()
        self.optimizer = FleetOptimizer()
        self.trust = TrustEngine()
        self.risk = RiskEngine()

    async def _policy(self, db: AsyncSession) -> dict:
        row = (await db.execute(
            select(FleetPolicy).where(FleetPolicy.is_default.is_(True)).limit(1)
        )).scalar_one_or_none()
        if row:
            return {"name": row.name, "version": row.version, "settings_json": dict(row.settings_json or {})}
        return {"name": "CONSERVATIVE", "version": 1, "settings_json": dict(CONSERVATIVE_POLICY_SETTINGS)}

    async def _account_inputs(self, db: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
        fleets = list((await db.execute(select(FleetAccount).limit(limit))).scalars().all())
        out: list[dict[str, Any]] = []
        for f in fleets:
            acc = (await db.execute(select(Account).where(Account.id == f.account_id))).scalar_one_or_none()
            evidence = {
                "active_days": float(getattr(acc, "days_active", 0) or 0) if acc else 0,
                "ramp_day_index": min(int(getattr(acc, "days_active", 0) or 0), 6) if acc else 0,
            }
            trust = self.trust.evaluate(evidence, {})
            risk = self.risk.evaluate(evidence, [], {})
            out.append({
                "account_id": str(f.account_id),
                "fleet_state": f.fleet_state,
                "trust_score": trust.score,
                "risk_level": risk.level,
                "used_today": int(getattr(acc, "sent_today", 0) or 0) if acc else 0,
                "evidence": evidence,
                "cutover": bool(f.cutover),
            })
        return out

    async def capacity_preview(self, db: AsyncSession, account_id: uuid.UUID | None = None) -> dict:
        policy = await self._policy(db)
        accounts = await self._account_inputs(db)
        if account_id:
            accounts = [a for a in accounts if a["account_id"] == str(account_id)]
        plans = []
        for a in accounts:
            cap = self.capacity.evaluate(
                fleet_state=a["fleet_state"],
                policy=policy,
                evidence=a["evidence"],
                trust_score=a["trust_score"],
                risk_level=a["risk_level"],
                used_today=a["used_today"],
            )
            bud = self.budget.compute(
                daily_capacity=cap.daily_capacity,
                used_today=a["used_today"],
                policy=policy,
            )
            plans.append({
                "account_id": a["account_id"],
                "capacity": cap.as_dict(),
                "budget": bud.as_dict(),
                "cutover": a["cutover"],
            })
        return {
            "simulation_only": True,
            "mutates_runtime": False,
            "plans": plans,
            "optimizer": self.optimizer.recommend(accounts).as_dict(),
        }

    async def campaign_plan_simulate(
        self,
        db: AsyncSession,
        *,
        campaign: dict | None = None,
        persist: bool = False,
    ) -> dict:
        policy = await self._policy(db)
        accounts = await self._account_inputs(db)
        plan = self.campaign.plan(campaign=campaign or {}, accounts=accounts, policy=policy)
        out = {
            "simulation_only": True,
            "mutates_runtime": False,
            "executes_campaign": False,
            "plan": plan.as_dict(),
            "dry_run": not persist,
        }
        if persist:
            snap = FleetPlanSnapshot(
                id=uuid.uuid4(),
                plan_type="campaign",
                payload_json=out,
                planner_version=plan.planner_version,
                simulation_only=True,
            )
            db.add(snap)
            await db.flush()
            out["snapshot_id"] = str(snap.id)
            out["persisted"] = True
        return out

    async def schedule_preview(self, db: AsyncSession, account_id: str | None = None) -> dict:
        policy = await self._policy(db)
        sched = self.schedule.preview(policy=policy, account_id=account_id or "fleet")
        return {"simulation_only": True, "executes": False, "schedule": sched.as_dict()}
