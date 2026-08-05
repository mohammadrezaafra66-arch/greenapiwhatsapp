"""V67 Phase 4 — Readiness evaluator (recommendations only; never changes FleetState)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

from app.services.fleet_state import FleetState
from app.services.graduation_trial import GraduationTrialFramework

ReadinessLabel = str  # NOT_READY | READY_FOR_TRIAL | READY_FOR_CAMPAIGN | READY_FOR_MATURE


@dataclass(frozen=True)
class ReadinessResult:
    label: ReadinessLabel
    score: float
    reasons: tuple[str, ...]
    mutates_fleet_state: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reasons"] = list(self.reasons)
        return d


class ReadinessEvaluator:
    """Combine trust/risk/graduation into a recommendation label only."""

    def evaluate(
        self,
        *,
        current_fleet_state: str,
        trust_score: float,
        risk_level: str,
        risk_score: float,
        evidence: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> ReadinessResult:
        evidence = evidence or {}
        policy = policy or {}
        trial = GraduationTrialFramework().evaluate(
            current_fleet_state=current_fleet_state,
            trust_score=trust_score,
            risk_level=risk_level,
            evidence=evidence,
            policy=policy,
        )

        # Phase 4: never emit READY_FOR_CAMPAIGN / READY_FOR_MATURE as actionable auto-grant.
        # Those labels may appear only as informational "future path" when explicitly simulated
        # with inject_future_path — default is NOT_READY or READY_FOR_TRIAL.
        if risk_level in ("HIGH", "CRITICAL"):
            return ReadinessResult(
                "NOT_READY",
                score=max(0.0, 100.0 - risk_score),
                reasons=("risk_too_high",) + trial.reason_codes,
            )

        if trial.eligible:
            return ReadinessResult(
                "READY_FOR_TRIAL",
                score=min(100.0, trust_score),
                reasons=trial.reason_codes,
            )

        # Informational only — Phase 4 does not authorize campaign/mature
        if evidence.get("simulate_future_campaign_path") and trust_score >= 80 and risk_level == "NORMAL":
            return ReadinessResult(
                "READY_FOR_CAMPAIGN",
                score=trust_score,
                reasons=("informational_future_path_only", "phase4_does_not_apply"),
            )
        if evidence.get("simulate_future_mature_path") and trust_score >= 90 and risk_level == "NORMAL":
            return ReadinessResult(
                "READY_FOR_MATURE",
                score=trust_score,
                reasons=("informational_future_path_only", "phase4_does_not_apply"),
            )

        reasons = trial.reason_codes or ("not_ready",)
        if current_fleet_state != FleetState.WARMUP_READY.value:
            reasons = ("fleet_state_not_warmup_ready",) + reasons
        return ReadinessResult(
            "NOT_READY",
            score=max(0.0, trust_score - risk_score * 0.5),
            reasons=reasons,
        )
