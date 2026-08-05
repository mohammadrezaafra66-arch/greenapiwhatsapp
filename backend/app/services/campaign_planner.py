"""V67 Phase 5 — Campaign Planner (simulation only; never executes campaigns)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any

from app.services.capacity_planner import CapacityPlanner
from app.services.fleet_budget import FleetBudgetEngine
from app.services.schedule_planner import SchedulePlanner
from app.services.fleet_optimizer import FleetOptimizer
from app.services.fleet_state import FleetState

CAMPAIGN_PLANNER_VERSION = "v67.5.campaign.1"


@dataclass(frozen=True)
class CampaignPlan:
    recommended_accounts: tuple[str, ...]
    recommended_batches: tuple[dict[str, Any], ...]
    recommended_start: str | None
    recommended_stop: str | None
    recommended_spacing_minutes: int
    estimated_completion: str | None
    estimated_risk: str
    capacity_summary: dict[str, Any]
    budget_summary: dict[str, Any]
    schedule_preview: dict[str, Any]
    optimizer: dict[str, Any]
    reason_codes: tuple[str, ...]
    planner_version: str
    simulation_only: bool = True
    executes_campaign: bool = False
    mutates_runtime: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["recommended_accounts"] = list(self.recommended_accounts)
        d["recommended_batches"] = list(self.recommended_batches)
        d["reason_codes"] = list(self.reason_codes)
        return d


class CampaignPlanner:
    """Recommend campaign shape. Never starts campaigns or sends messages."""

    version = CAMPAIGN_PLANNER_VERSION

    def __init__(self):
        self.capacity = CapacityPlanner()
        self.budget = FleetBudgetEngine()
        self.schedule = SchedulePlanner()
        self.optimizer = FleetOptimizer()

    def plan(
        self,
        *,
        campaign: dict[str, Any] | None = None,
        accounts: list[dict[str, Any]] | None = None,
        policy: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> CampaignPlan:
        campaign = campaign or {}
        accounts = list(accounts or [])
        policy = policy or {}
        now = now or datetime.utcnow()
        reasons: list[str] = []

        target = int(campaign.get("target_messages") or campaign.get("contact_count") or 100)
        spacing = int(campaign.get("spacing_minutes") or policy.get("spacing_minutes") or 20)
        batch_size = int(campaign.get("batch_size") or 10)

        opt = self.optimizer.recommend(accounts)
        recommended_ids = list(opt.best_accounts)
        if not recommended_ids:
            # fall back to rest (warmup-ready) for simulation visibility — still not executable
            recommended_ids = list(opt.rest_accounts)
            reasons.append("no_campaign_ready_accounts_using_rest_for_sim")
        else:
            reasons.append("using_optimizer_best_accounts")

        # Aggregate capacity across recommended accounts
        fleet_caps = []
        for a in accounts:
            if str(a.get("account_id")) not in recommended_ids:
                continue
            cap = self.capacity.evaluate(
                fleet_state=str(a.get("fleet_state") or FleetState.WARMUP_READY.value),
                policy=policy,
                evidence=a.get("evidence") or {},
                trust_score=float(a.get("trust_score") or 50),
                risk_level=str(a.get("risk_level") or "NORMAL"),
                fleet_account_count=1,
                used_today=int(a.get("used_today") or 0),
            )
            fleet_caps.append(cap)

        daily_total = sum(c.daily_capacity for c in fleet_caps) if fleet_caps else 0
        campaign_total = sum(c.campaign_budget for c in fleet_caps) if fleet_caps else 0
        if campaign_total <= 0 and daily_total > 0:
            # Simulation note: accounts not campaign-capable yet
            reasons.append("zero_campaign_budget_accounts_not_campaign_ready")
            campaign_total = 0

        bud = self.budget.compute(
            daily_capacity=max(campaign_total, 0),
            used_today=0,
            policy=policy,
        )

        # Batches from recommended usage
        usable = bud.recommended_usage if campaign_total > 0 else 0
        batches: list[dict[str, Any]] = []
        remaining = min(target, usable) if usable else 0
        idx = 0
        while remaining > 0 and recommended_ids:
            n = min(batch_size, remaining)
            aid = recommended_ids[idx % len(recommended_ids)]
            batches.append({
                "batch_index": len(batches),
                "account_id": aid,
                "message_count": n,
                "status": "SIMULATED_ONLY",
            })
            remaining -= n
            idx += 1

        sched = self.schedule.preview(
            now=now,
            policy=policy,
            account_id=recommended_ids[0] if recommended_ids else "fleet",
            batch_count=max(1, len(batches)),
            messages_per_batch=batch_size,
            spacing_minutes=spacing,
        )
        start = sched.slots[0]["scheduled_at"] if sched.slots else None
        stop = sched.slots[-1]["scheduled_at"] if sched.slots else None
        # estimated completion: last slot + spacing
        if stop:
            try:
                est = datetime.fromisoformat(stop) + timedelta(minutes=spacing)
                completion = est.isoformat()
            except Exception:
                completion = stop
        else:
            completion = None

        # Estimated risk = worst risk among recommended
        risk_order = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        est_risk = "NORMAL"
        for a in accounts:
            if str(a.get("account_id")) in recommended_ids:
                lvl = str(a.get("risk_level") or "NORMAL")
                if risk_order.get(lvl, 0) > risk_order.get(est_risk, 0):
                    est_risk = lvl

        if not batches:
            reasons.append("no_batches_planned")

        return CampaignPlan(
            recommended_accounts=tuple(recommended_ids),
            recommended_batches=tuple(batches),
            recommended_start=start,
            recommended_stop=stop,
            recommended_spacing_minutes=spacing,
            estimated_completion=completion,
            estimated_risk=est_risk,
            capacity_summary={
                "daily_total": daily_total,
                "campaign_total": campaign_total,
                "accounts_evaluated": len(fleet_caps),
            },
            budget_summary=bud.as_dict(),
            schedule_preview=sched.as_dict(),
            optimizer=opt.as_dict(),
            reason_codes=tuple(reasons),
            planner_version=self.version,
        )
