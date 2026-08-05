"""V67 Phase 5 — Capacity Planner (simulation recommendations only)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

from app.services.fleet_policy_defaults import CONSERVATIVE_RAMP_CURVE, validate_policy_settings
from app.services.fleet_state import FleetState

PLANNER_VERSION = "v67.5.capacity.1"

_RISK_FACTOR = {
    "NORMAL": 1.0,
    "LOW": 0.85,
    "MEDIUM": 0.55,
    "HIGH": 0.25,
    "CRITICAL": 0.0,
}

# States eligible for campaign-oriented capacity (recommendation only)
_CAMPAIGN_CAPABLE = frozenset({
    FleetState.GRADUATION_TRIAL.value,
    FleetState.CAMPAIGN_READY.value,
    FleetState.MATURE.value,
    FleetState.MAINTENANCE.value,
})

_ZERO_CAPACITY = frozenset({
    FleetState.NEW.value,
    FleetState.PRECHECK.value,
    FleetState.QR_WAITING.value,
    FleetState.READY_TO_LINK.value,
    FleetState.SUSPENDED.value,
    FleetState.BLOCKED.value,
    FleetState.FORCED_LOGOUT.value,
    FleetState.REWARM_REQUIRED.value,
    FleetState.FAILED.value,
    FleetState.RETIRED.value,
    FleetState.PAUSED.value,
})


@dataclass(frozen=True)
class CapacityPlan:
    daily_capacity: int
    hourly_capacity: float
    account_budget: int
    campaign_budget: int
    fleet_budget: int
    base_from_policy: int
    trust_weight: float
    risk_factor: float
    fleet_state: str
    reason_codes: tuple[str, ...]
    planner_version: str
    simulation_only: bool = True
    mutates_runtime: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason_codes"] = list(self.reason_codes)
        d["implemented"] = True
        d["phase"] = 5
        return d


class CapacityPlanner:
    """Deterministic capacity recommendations. Never sends / mutates / enqueues."""

    version = PLANNER_VERSION

    def plan(
        self,
        fleet_state: str,
        policy: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        *,
        trust_score: float = 50.0,
        risk_level: str = "NORMAL",
        fleet_account_count: int = 1,
        used_today: int = 0,
    ) -> dict[str, Any]:
        return self.evaluate(
            fleet_state=fleet_state,
            policy=policy,
            evidence=evidence,
            trust_score=trust_score,
            risk_level=risk_level,
            fleet_account_count=fleet_account_count,
            used_today=used_today,
        ).as_dict()

    def evaluate(
        self,
        *,
        fleet_state: str,
        policy: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        trust_score: float = 50.0,
        risk_level: str = "NORMAL",
        fleet_account_count: int = 1,
        used_today: int = 0,
    ) -> CapacityPlan:
        evidence = evidence or {}
        policy = policy or {}
        settings = policy.get("settings_json") or policy.get("settings") or policy
        reasons: list[str] = []

        ok, msg = validate_policy_settings(settings if isinstance(settings, dict) else {})
        if not ok and settings:
            reasons.append(f"policy_invalid:{msg}")
            return CapacityPlan(
                0, 0.0, 0, 0, 0, 0, 0.0, 0.0, fleet_state,
                tuple(reasons), self.version,
            )

        curve = list((settings or {}).get("ramp_curve") or CONSERVATIVE_RAMP_CURVE)
        if not curve:
            curve = list(CONSERVATIVE_RAMP_CURVE)
        day_index = int(evidence.get("ramp_day_index") or evidence.get("active_days") or 0)
        day_index = max(0, min(day_index, len(curve) - 1))
        base = int(curve[day_index])
        flow_max = int((settings or {}).get("total_flow_max") or curve[-1])
        base = min(base, flow_max)

        state = (fleet_state or FleetState.NEW.value).strip()
        if state in _ZERO_CAPACITY:
            reasons.append("state_zero_capacity")
            return CapacityPlan(
                0, 0.0, 0, 0, 0, base, 0.0, 0.0, state,
                tuple(reasons), self.version,
            )

        trust_w = max(0.0, min(1.0, float(trust_score) / 100.0))
        risk_f = float(_RISK_FACTOR.get(risk_level, 0.0))
        if risk_f <= 0:
            reasons.append("risk_blocks_capacity")

        # Warmup states: capacity is total-flow recommendation, not campaign sends
        if state not in _CAMPAIGN_CAPABLE:
            reasons.append("warmup_or_building_capacity_only")
            campaign_share = 0.0
        else:
            reasons.append("campaign_capable_state")
            campaign_share = 0.7

        working_hours = float((settings or {}).get("working_hours_per_day") or 10)
        working_hours = max(1.0, working_hours)

        raw = base * trust_w * risk_f
        daily = int(max(0, round(raw)))
        # Maintenance soft cap
        if state == FleetState.MAINTENANCE.value:
            maint = int((settings or {}).get("maintenance_flow") or 10)
            daily = min(daily, maint)
            reasons.append("maintenance_cap")

        hourly = round(daily / working_hours, 2) if daily else 0.0
        account_budget = max(0, daily - int(used_today or 0))
        campaign_budget = int(round(account_budget * campaign_share))
        n = max(1, int(fleet_account_count or 1))
        fleet_budget = daily * n

        reasons.append(f"base_{base}")
        reasons.append(f"trust_w_{trust_w:.2f}")
        reasons.append(f"risk_f_{risk_f:.2f}")

        return CapacityPlan(
            daily_capacity=daily,
            hourly_capacity=hourly,
            account_budget=account_budget,
            campaign_budget=campaign_budget,
            fleet_budget=fleet_budget,
            base_from_policy=base,
            trust_weight=round(trust_w, 4),
            risk_factor=risk_f,
            fleet_state=state,
            reason_codes=tuple(reasons),
            planner_version=self.version,
        )
