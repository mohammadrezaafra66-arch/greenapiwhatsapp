"""V67 Phase 5 — Fleet Budget Engine (outputs only; no mutation)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

BUDGET_VERSION = "v67.5.budget.1"


@dataclass(frozen=True)
class FleetBudget:
    daily_budget: int
    hourly_budget: float
    remaining_budget: int
    safety_reserve: int
    reserve_ratio: float
    recommended_usage: int
    used_today: int
    reason_codes: tuple[str, ...]
    budget_version: str
    simulation_only: bool = True
    mutates_runtime: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason_codes"] = list(self.reason_codes)
        return d


class FleetBudgetEngine:
    """Derive Daily/Hourly/Remaining/SafetyReserve/RecommendedUsage from capacity."""

    version = BUDGET_VERSION

    def compute(
        self,
        *,
        daily_capacity: int,
        used_today: int = 0,
        working_hours: float = 10.0,
        reserve_ratio: float | None = None,
        policy: dict[str, Any] | None = None,
    ) -> FleetBudget:
        settings = (policy or {}).get("settings_json") or (policy or {}).get("settings") or (policy or {})
        ratio = reserve_ratio
        if ratio is None:
            ratio = float(settings.get("safety_reserve_ratio") or 0.15)
        ratio = max(0.0, min(0.5, float(ratio)))
        working_hours = max(1.0, float(working_hours or 10.0))
        daily = max(0, int(daily_capacity))
        used = max(0, int(used_today))
        remaining = max(0, daily - used)
        reserve = int(round(daily * ratio))
        recommended = max(0, remaining - reserve)
        hourly = round(daily / working_hours, 2) if daily else 0.0
        return FleetBudget(
            daily_budget=daily,
            hourly_budget=hourly,
            remaining_budget=remaining,
            safety_reserve=reserve,
            reserve_ratio=ratio,
            recommended_usage=recommended,
            used_today=used,
            reason_codes=(
                f"daily_{daily}",
                f"reserve_ratio_{ratio}",
                f"recommended_{recommended}",
            ),
            budget_version=self.version,
        )
