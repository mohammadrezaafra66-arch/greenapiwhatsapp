"""V67 Phase 4 — Graduation Trial framework (simulation recommendations only)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

from app.services.fleet_state import FleetState


@dataclass(frozen=True)
class GraduationTrialDecision:
    eligible: bool
    from_state: str
    recommended_state: str  # GRADUATION_TRIAL or stay
    reason_codes: tuple[str, ...]
    missing: tuple[str, ...]
    simulation_only: bool = True
    applies_fleet_state: bool = False  # Phase 4 never applies

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason_codes"] = list(self.reason_codes)
        d["missing"] = list(self.missing)
        return d


DEFAULT_TRIAL_REQUIREMENTS = {
    "min_trust_score": 55.0,
    "max_risk_level": "LOW",  # NORMAL or LOW allowed
    "require_warmup_ready": True,
    "min_incident_free_days": 7,
    "min_bidirectional_chats": 2,
    "require_day10": True,
}


_RISK_ORDER = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


class GraduationTrialFramework:
    """Framework only — never starts campaigns or mutates FleetState."""

    def evaluate(
        self,
        *,
        current_fleet_state: str,
        trust_score: float,
        risk_level: str,
        evidence: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> GraduationTrialDecision:
        evidence = evidence or {}
        policy = policy or {}
        req = dict(DEFAULT_TRIAL_REQUIREMENTS)
        req.update(policy.get("graduation_trial") or policy.get("graduation_requirements_placeholder") or {})

        missing: list[str] = []
        reasons: list[str] = []
        cur = current_fleet_state or FleetState.NEW.value

        if req.get("require_warmup_ready", True) and cur != FleetState.WARMUP_READY.value:
            reasons.append("not_warmup_ready")
            return GraduationTrialDecision(
                False, cur, cur, tuple(reasons), tuple(missing),
            )

        min_trust = float(req.get("min_trust_score", 55))
        if trust_score < min_trust:
            missing.append("trust_score")
            reasons.append(f"trust_below_{min_trust}")

        max_risk = str(req.get("max_risk_level", "LOW"))
        if _RISK_ORDER.get(risk_level, 99) > _RISK_ORDER.get(max_risk, 1):
            missing.append("risk_level")
            reasons.append(f"risk_above_{max_risk}")

        ifree = evidence.get("incident_free_days")
        min_ifree = float(req.get("min_incident_free_days", 7))
        if ifree is None or float(ifree) < min_ifree:
            missing.append("incident_free_days")
            reasons.append("incident_free_days_insufficient")

        bi = evidence.get("bidirectional_chats") or 0
        if float(bi) < float(req.get("min_bidirectional_chats", 2)):
            missing.append("bidirectional_chats")
            reasons.append("bidirectional_insufficient")

        if req.get("require_day10", True) and not (
            evidence.get("day10_complete") or (evidence.get("active_days") or 0) >= 10
        ):
            missing.append("day10_complete")
            reasons.append("day10_not_complete")

        # Never auto CAMPAIGN_READY / MATURE
        if missing:
            return GraduationTrialDecision(
                False, cur, FleetState.WARMUP_READY.value if cur == FleetState.WARMUP_READY.value else cur,
                tuple(reasons) or ("requirements_unmet",), tuple(missing),
            )

        reasons.append("eligible_for_graduation_trial_simulation")
        return GraduationTrialDecision(
            True,
            cur,
            FleetState.GRADUATION_TRIAL.value,
            tuple(reasons),
            (),
            simulation_only=True,
            applies_fleet_state=False,
        )
