"""V67 Phase 5 — Fleet Optimizer (recommendations only; no mutation)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

from app.services.fleet_state import FleetState

OPTIMIZER_VERSION = "v67.5.optimizer.1"


@dataclass(frozen=True)
class OptimizerRecommendation:
    best_accounts: tuple[str, ...]
    rest_accounts: tuple[str, ...]
    cooldown_accounts: tuple[str, ...]
    maintenance_accounts: tuple[str, ...]
    rewarm_accounts: tuple[str, ...]
    reason_codes: tuple[str, ...]
    optimizer_version: str
    simulation_only: bool = True
    mutates_accounts: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("best_accounts", "rest_accounts", "cooldown_accounts",
                  "maintenance_accounts", "rewarm_accounts", "reason_codes"):
            d[k] = list(d[k])
        return d


class FleetOptimizer:
    """Classify accounts into recommended buckets from sensors/scores."""

    version = OPTIMIZER_VERSION

    def recommend(self, accounts: list[dict[str, Any]]) -> OptimizerRecommendation:
        """Each account dict: account_id, fleet_state, trust_score, risk_level, evidence?"""
        best: list[str] = []
        rest: list[str] = []
        cooldown: list[str] = []
        maintenance: list[str] = []
        rewarm: list[str] = []
        reasons: list[str] = []

        for a in accounts or []:
            aid = str(a.get("account_id") or "")
            if not aid:
                continue
            state = str(a.get("fleet_state") or "")
            trust = float(a.get("trust_score") or 0)
            risk = str(a.get("risk_level") or "NORMAL")

            if state in (
                FleetState.REWARM_REQUIRED.value, FleetState.BLOCKED.value,
                FleetState.SUSPENDED.value, FleetState.FORCED_LOGOUT.value,
            ):
                rewarm.append(aid)
                continue
            if state == FleetState.MAINTENANCE.value:
                maintenance.append(aid)
                continue
            if state in (FleetState.PAUSED.value, FleetState.AT_RISK.value) or risk in ("HIGH", "CRITICAL"):
                cooldown.append(aid)
                continue
            if state in (
                FleetState.CAMPAIGN_READY.value, FleetState.MATURE.value,
                FleetState.GRADUATION_TRIAL.value,
            ) and trust >= 55 and risk in ("NORMAL", "LOW"):
                best.append(aid)
                continue
            if state == FleetState.WARMUP_READY.value and trust >= 40:
                rest.append(aid)  # rest / hold for trial — not campaign best
                continue
            rest.append(aid)

        reasons.append(f"best_{len(best)}")
        reasons.append(f"rest_{len(rest)}")
        reasons.append(f"cooldown_{len(cooldown)}")
        reasons.append(f"maintenance_{len(maintenance)}")
        reasons.append(f"rewarm_{len(rewarm)}")
        return OptimizerRecommendation(
            best_accounts=tuple(best),
            rest_accounts=tuple(rest),
            cooldown_accounts=tuple(cooldown),
            maintenance_accounts=tuple(maintenance),
            rewarm_accounts=tuple(rewarm),
            reason_codes=tuple(reasons),
            optimizer_version=self.version,
        )
