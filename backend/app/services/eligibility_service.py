"""V67 Phase 6 — eligibility simulation facade (read sensors; decide; never mutate)."""
from __future__ import annotations
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.fleet_account import FleetAccount
from app.models.fleet_policy import FleetPolicy
from app.models.account_journey import AccountJourney
from app.models.fleet_plan import FleetPlanSnapshot
from app.services.campaign_eligibility import CampaignEligibilityEngine
from app.services.fleet_scoring import FleetScoringService
from app.services.capacity_planner import CapacityPlanner
from app.services.fleet_budget import FleetBudgetEngine
from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS
from app.services.journey_types import JourneyStatus


class EligibilityService:
    def __init__(self):
        self.engine = CampaignEligibilityEngine()
        self.scoring = FleetScoringService()
        self.capacity = CapacityPlanner()
        self.budget = FleetBudgetEngine()

    async def _policy(self, db: AsyncSession) -> tuple[dict, int | None]:
        row = (await db.execute(
            select(FleetPolicy).where(FleetPolicy.is_default.is_(True)).limit(1)
        )).scalar_one_or_none()
        if row:
            return (
                {"name": row.name, "version": row.version, "settings_json": dict(row.settings_json or {})},
                int(row.version),
            )
        # Ensure eligibility_rules present even on empty DB
        settings = dict(CONSERVATIVE_POLICY_SETTINGS)
        return {"name": "CONSERVATIVE", "version": 1, "settings_json": settings}, 1

    async def preview(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        *,
        inject: dict | None = None,
        persist: bool = False,
    ) -> dict[str, Any]:
        inject = inject or {}
        fleet = (await db.execute(
            select(FleetAccount).where(FleetAccount.account_id == account_id)
        )).scalar_one_or_none()
        acc = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
        if acc is None:
            return {"error": "account_not_found"}

        policy, policy_version = await self._policy(db)
        # Prefer policy from DB; merge default eligibility_rules if older policy lacks them
        settings = dict(policy.get("settings_json") or {})
        if "eligibility_rules" not in settings:
            settings["eligibility_rules"] = dict(
                CONSERVATIVE_POLICY_SETTINGS.get("eligibility_rules") or {}
            )
            policy = {**policy, "settings_json": settings}

        score = await self.scoring.simulate(db, account_id, inject=inject, persist=False)
        if score.get("error"):
            return score

        evidence = dict(score.get("evidence") or {})
        if inject.get("breaker"):
            evidence["breaker"] = True
        breaker = bool(inject.get("breaker") or evidence.get("breaker") or evidence.get("fleet_breaker_tripped"))
        try:
            from app.services import fleet_breaker
            tripped, _ = await fleet_breaker.is_tripped(fail_closed=False)
            breaker = breaker or bool(tripped)
        except Exception:
            pass

        journey = (await db.execute(
            select(AccountJourney).where(
                AccountJourney.account_id == account_id,
                AccountJourney.status.in_([
                    JourneyStatus.ACTIVE.value, JourneyStatus.PAUSED.value, JourneyStatus.SIMULATING.value,
                ]),
            ).limit(1)
        )).scalar_one_or_none()

        fleet_state = fleet.fleet_state if fleet else "NEW"
        if inject.get("fleet_state"):
            fleet_state = str(inject["fleet_state"])

        trust_score = float(score["trust"]["score"])
        risk_level = str(score["risk"]["level"])
        readiness = str(score["readiness"]["label"])
        if inject.get("trust_score") is not None:
            trust_score = float(inject["trust_score"])
        if inject.get("risk_level"):
            risk_level = str(inject["risk_level"])
        if inject.get("readiness_label"):
            readiness = str(inject["readiness_label"])

        cap = self.capacity.evaluate(
            fleet_state=fleet_state,
            policy=policy,
            evidence=evidence,
            trust_score=trust_score,
            risk_level=risk_level,
            used_today=int(getattr(acc, "sent_today", 0) or 0),
        )
        bud = self.budget.compute(
            daily_capacity=cap.daily_capacity,
            used_today=int(getattr(acc, "sent_today", 0) or 0),
            policy=policy,
        )
        if inject.get("daily_capacity") is not None:
            daily_capacity = int(inject["daily_capacity"])
            recommended_usage = int(inject.get("recommended_usage", daily_capacity))
            remaining = int(inject.get("remaining_budget", recommended_usage))
        else:
            daily_capacity = cap.daily_capacity
            recommended_usage = bud.recommended_usage
            remaining = bud.remaining_budget

        decision = self.engine.decide(
            fleet_state=fleet_state,
            journey_status=journey.status if journey else None,
            trust_score=trust_score,
            risk_level=risk_level,
            readiness_label=readiness,
            daily_capacity=daily_capacity,
            recommended_usage=recommended_usage,
            remaining_budget=remaining,
            policy=policy,
            incidents=list(evidence.get("incidents") or []),
            breaker_tripped=breaker,
            evidence=evidence,
            policy_version=policy_version,
        )

        out = {
            "simulation_only": True,
            "mutates_runtime": False,
            "executes": False,
            "account_id": str(account_id),
            "canonical_fleet_state": fleet.fleet_state if fleet else None,
            "evaluated_fleet_state": fleet_state,
            "cutover": bool(fleet.cutover) if fleet else False,
            "decision": decision.as_dict(),
            "inputs": {
                "trust_score": trust_score,
                "risk_level": risk_level,
                "readiness_label": readiness,
                "daily_capacity": daily_capacity,
                "recommended_usage": recommended_usage,
                "remaining_budget": remaining,
                "breaker_tripped": breaker,
                "journey_status": journey.status if journey else None,
            },
            "send_gate_note": "unchanged — eligibility does not call or alter send_gate",
            "dry_run": not persist,
        }
        if persist:
            if fleet and fleet.cutover:
                out["persisted"] = False
                out["error"] = "cutover_true_forbidden_for_phase6_persist"
                return out
            snap = FleetPlanSnapshot(
                id=uuid.uuid4(),
                plan_type="eligibility",
                payload_json=out,
                planner_version=decision.decision_version,
                simulation_only=True,
            )
            db.add(snap)
            await db.flush()
            out["snapshot_id"] = str(snap.id)
            out["persisted"] = True
        return out

    async def fleet_eligibility(self, db: AsyncSession, limit: int = 100) -> dict[str, Any]:
        fleets = list((await db.execute(select(FleetAccount).limit(limit))).scalars().all())
        rows = []
        for f in fleets:
            row = await self.preview(db, f.account_id, persist=False)
            if row.get("error"):
                continue
            rows.append({
                "account_id": str(f.account_id),
                "fleet_state": f.fleet_state,
                "decision": row["decision"]["decision"],
                "reason_codes": row["decision"]["reason_codes"],
            })
        return {"simulation_only": True, "mutates_runtime": False, "accounts": rows}
