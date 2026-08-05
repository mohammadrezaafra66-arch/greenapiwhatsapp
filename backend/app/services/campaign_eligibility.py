"""V67 Phase 6.1 — Campaign Eligibility Engine (decisions only; never executes).

Decision version bumped to v67.6.eligibility.2 for fail-closed semantics.
No silent policy fallback inside the pure engine.
"""
from __future__ import annotations
import enum
from dataclasses import dataclass, asdict, field
from typing import Any

from app.services.fleet_policy_defaults import validate_policy_settings
from app.services.eligibility_policy import (
    validate_eligibility_rules, VALID_RISK, VALID_READINESS, FLEET_SET, _RISK_ORDER,
)
from app.services.journey_types import JourneyStatus

_VALID_JOURNEY = frozenset(s.value for s in JourneyStatus)

DECISION_VERSION = "v67.6.eligibility.2"


class EligibilityLabel(str, enum.Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ELIGIBLE_FOR_TRIAL = "ELIGIBLE_FOR_TRIAL"
    ELIGIBLE_FOR_LIMITED_CAMPAIGN = "ELIGIBLE_FOR_LIMITED_CAMPAIGN"
    ELIGIBLE_FOR_STANDARD_CAMPAIGN = "ELIGIBLE_FOR_STANDARD_CAMPAIGN"
    ELIGIBLE_FOR_HIGH_VOLUME = "ELIGIBLE_FOR_HIGH_VOLUME"


_TIER_META = (
    (EligibilityLabel.ELIGIBLE_FOR_HIGH_VOLUME, "high_volume_fleet_states", "high_volume_min_trust",
     "high_volume_max_risk", "require_readiness_for_high_volume",
     "min_daily_capacity_high_volume", "min_recommended_usage_high_volume"),
    (EligibilityLabel.ELIGIBLE_FOR_STANDARD_CAMPAIGN, "standard_fleet_states", "standard_min_trust",
     "standard_max_risk", "require_readiness_for_standard",
     "min_daily_capacity_standard", "min_recommended_usage_standard"),
    (EligibilityLabel.ELIGIBLE_FOR_LIMITED_CAMPAIGN, "limited_fleet_states", "limited_min_trust",
     "limited_max_risk", "require_readiness_for_limited",
     "min_daily_capacity_limited", "min_recommended_usage_limited"),
    (EligibilityLabel.ELIGIBLE_FOR_TRIAL, "trial_fleet_states", "trial_min_trust",
     "trial_max_risk", "require_readiness_for_trial",
     "min_daily_capacity_trial", "min_recommended_usage_trial"),
)

_NEXT = {
    EligibilityLabel.ELIGIBLE_FOR_HIGH_VOLUME: "simulate_high_volume_plan_only",
    EligibilityLabel.ELIGIBLE_FOR_STANDARD_CAMPAIGN: "simulate_standard_campaign_plan_only",
    EligibilityLabel.ELIGIBLE_FOR_LIMITED_CAMPAIGN: "simulate_limited_campaign_plan_only",
    EligibilityLabel.ELIGIBLE_FOR_TRIAL: "simulate_graduation_trial_only",
}


@dataclass(frozen=True)
class EligibilityDecision:
    decision: str  # serialized EligibilityLabel value
    reason_codes: tuple[str, ...]
    blocking_evidence: tuple[str, ...]
    required_evidence: tuple[str, ...]
    next_recommendation: str
    policy_version: int | None
    decision_version: str
    simulation_only: bool = True
    mutates_runtime: bool = False
    executes: bool = False
    policy_source: str | None = None
    closest_tier: str | None = None
    tier_gaps: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason_codes"] = list(self.reason_codes)
        d["blocking_evidence"] = list(self.blocking_evidence)
        d["required_evidence"] = list(self.required_evidence)
        d["tier_gaps"] = [dict(g) for g in self.tier_gaps]
        return d


def _settings(policy: dict | None) -> dict | None:
    if policy is None:
        return None
    if not isinstance(policy, dict):
        return None
    nested = policy.get("settings_json")
    if nested is not None:
        return nested if isinstance(nested, dict) else None
    nested = policy.get("settings")
    if nested is not None:
        return nested if isinstance(nested, dict) else None
    # Treat bare settings object (must contain eligibility_rules key or known policy keys)
    if "eligibility_rules" in policy or "ramp_curve" in policy or "flow_metric" in policy:
        return policy
    return policy


def _risk_ok(level: str, max_level: str) -> bool:
    if level not in _RISK_ORDER or max_level not in _RISK_ORDER:
        return False
    return _RISK_ORDER[level] <= _RISK_ORDER[max_level]


def _deny(
    *reason_codes: str,
    blocking: tuple[str, ...] = (),
    required: tuple[str, ...] = (),
    next_recommendation: str = "fix_or_provide_valid_policy",
    policy_version: int | None = None,
    policy_source: str | None = None,
    closest_tier: str | None = None,
    tier_gaps: tuple[dict[str, Any], ...] = (),
) -> EligibilityDecision:
    return EligibilityDecision(
        EligibilityLabel.NOT_ELIGIBLE.value,
        reason_codes,
        blocking,
        required,
        next_recommendation,
        policy_version,
        DECISION_VERSION,
        policy_source=policy_source,
        closest_tier=closest_tier,
        tier_gaps=tier_gaps,
    )


class CampaignEligibilityEngine:
    """Pure deterministic eligibility decisions. No IO / send / mutation."""

    version = DECISION_VERSION

    def decide(
        self,
        *,
        fleet_state: str,
        journey_status: str | None = None,
        trust_score: float = 0.0,
        risk_level: str = "CRITICAL",
        readiness_label: str | None = None,
        daily_capacity: int = 0,
        recommended_usage: int = 0,
        remaining_budget: int | None = None,
        policy: dict | None = None,
        incidents: list[str] | None = None,
        breaker_tripped: bool = False,
        evidence: dict | None = None,
        policy_version: int | None = None,
        policy_source: str | None = None,
    ) -> EligibilityDecision:
        evidence = evidence or {}
        incidents = [str(i) for i in (incidents or []) if i]
        for i in evidence.get("incidents") or []:
            if i and str(i) not in incidents:
                incidents.append(str(i))
        policy_source = policy_source or evidence.get("policy_source")

        if policy is None:
            return _deny(
                "policy_missing",
                blocking=("policy",),
                required=("valid_policy",),
                policy_version=policy_version,
                policy_source=policy_source,
            )

        settings = _settings(policy)
        if not isinstance(settings, dict) or not settings:
            return _deny(
                "policy_missing",
                blocking=("policy",),
                required=("valid_policy",),
                policy_version=policy_version,
                policy_source=policy_source,
            )

        ok, msg = validate_policy_settings(settings)
        if not ok:
            return _deny(
                f"policy_invalid:{msg}",
                blocking=("valid_policy",),
                required=("valid_policy",),
                policy_version=policy_version,
                policy_source=policy_source,
            )

        if "eligibility_rules" not in settings:
            return _deny(
                "eligibility_rules_missing",
                blocking=("eligibility_rules",),
                required=("eligibility_rules",),
                next_recommendation="add_eligibility_rules_to_policy",
                policy_version=policy_version,
                policy_source=policy_source,
            )

        rules = settings.get("eligibility_rules")
        rok, rmsg = validate_eligibility_rules(rules)
        if not rok:
            code = "eligibility_rules_missing" if "missing" in rmsg or rmsg.endswith("empty") else "eligibility_rules_invalid"
            return _deny(
                code if rmsg in ("eligibility_rules_missing", "eligibility_rules_empty") else f"{code}:{rmsg}",
                blocking=("eligibility_rules",),
                required=("valid_eligibility_rules",),
                next_recommendation="fix_eligibility_rules_in_policy",
                policy_version=policy_version,
                policy_source=policy_source,
            )

        if policy_version is None:
            return _deny(
                "policy_version_missing",
                blocking=("policy_version",),
                required=("policy_version",),
                next_recommendation="provide_auditable_policy_version",
                policy_version=None,
                policy_source=policy_source,
            )

        reasons: list[str] = []
        blocking: list[str] = []
        required: list[str] = []
        if policy_source:
            reasons.append(f"policy_source:{policy_source}")

        state = (fleet_state or "").strip()
        trust = float(trust_score or 0)
        risk = str(risk_level or "").strip() or "CRITICAL"
        readiness = (readiness_label or "").strip() or None
        capacity = int(daily_capacity or 0)
        usage = int(recommended_usage if recommended_usage is not None else 0)
        remaining = int(remaining_budget) if remaining_budget is not None else usage
        ifree = evidence.get("incident_free_days")

        # Unknown sensor fail-closed (policy gated)
        if rules.get("unknown_fleet_state_blocks", True) and state not in FLEET_SET:
            blocking.append("fleet_state")
            reasons.append(f"unknown_fleet_state:{state or 'empty'}")
        if rules.get("unknown_risk_blocks", True) and risk not in VALID_RISK:
            blocking.append("risk_level")
            reasons.append(f"unknown_risk_level:{risk}")
        if rules.get("unknown_readiness_blocks", True):
            if readiness is None or readiness not in VALID_READINESS:
                blocking.append("readiness_label")
                reasons.append(f"unknown_readiness:{readiness or 'missing'}")

        if rules.get("block_on_breaker", True) and breaker_tripped:
            blocking.append("breaker_tripped")
            reasons.append("breaker_blocks_eligibility")

        major = set(rules.get("major_incident_types") or [])
        if rules.get("block_on_open_major_incidents", True):
            hit = [i for i in incidents if i in major]
            if hit:
                blocking.append("open_major_incident")
                reasons.append(f"major_incidents:{','.join(sorted(hit))}")

        blocked_states = set(rules.get("blocked_fleet_states") or [])
        if state in blocked_states:
            blocking.append("fleet_state")
            reasons.append(f"fleet_state_blocked:{state}")

        min_ifree = rules.get("min_incident_free_days")
        if min_ifree is not None:
            if ifree is None:
                required.append("incident_free_days")
                blocking.append("incident_free_days_missing")
                reasons.append("incident_free_days_missing")
            elif float(ifree) < float(min_ifree):
                blocking.append("incident_free_days")
                reasons.append("incident_free_days_below_policy")

        # Journey fail-closed (policy-driven)
        hard_j = set(rules.get("journey_hard_block_statuses") or [])
        sim_j = set(rules.get("journey_simulation_only_statuses") or [])
        allow_j = set(rules.get("journey_allowed_for_eligibility") or [])
        jstat = journey_status
        if jstat is None or jstat == "":
            if rules.get("journey_missing_blocks", True):
                blocking.append("journey_status")
                reasons.append("journey_status_missing")
                required.append("journey_status")
        elif jstat in hard_j:
            blocking.append("journey_status")
            reasons.append(f"journey_status_hard_block:{jstat}")
        elif jstat in sim_j:
            blocking.append("journey_status")
            reasons.append(f"journey_simulating_not_operational:{jstat}")
        elif jstat not in allow_j:
            if jstat not in _VALID_JOURNEY:
                if rules.get("journey_unknown_blocks", True):
                    blocking.append("journey_status")
                    reasons.append(f"journey_status_unknown:{jstat}")
            else:
                blocking.append("journey_status")
                reasons.append(f"journey_status_not_allowed:{jstat}")
                required.append(f"journey_in:{','.join(sorted(allow_j))}")

        if blocking:
            return _deny(
                *(tuple(reasons) or ("blocked",)),
                blocking=tuple(dict.fromkeys(blocking)),
                required=tuple(dict.fromkeys(required + [
                    "healthy_fleet_state", "clear_breaker", "no_major_incidents", "allowed_journey_status",
                ])),
                next_recommendation="resolve_blocks_then_reevaluate",
                policy_version=policy_version,
                policy_source=policy_source,
            )

        tier_gaps: list[dict[str, Any]] = []

        def evaluate_tier(label: EligibilityLabel, sk, tk, rk, rdk, ck, uk) -> EligibilityDecision | None:
            states = set(rules.get(sk) or [])
            need_trust = float(rules.get(tk) or 0)
            max_risk = str(rules.get(rk) or "NORMAL")
            ready_ok = set(rules.get(rdk) or [])
            min_cap = int(rules.get(ck) or 0)
            min_usage = int(rules.get(uk) or 0)
            gap: dict[str, Any] = {
                "tier": label.value,
                "required_fleet_states": sorted(states),
                "required_trust": need_trust,
                "max_risk": max_risk,
                "required_readiness": sorted(ready_ok),
                "min_daily_capacity": min_cap,
                "min_recommended_usage": min_usage,
                "failed": [],
            }
            if state not in states:
                gap["failed"].append(f"fleet_state_not_in_tier:{state}")
                tier_gaps.append(gap)
                return None
            local_reasons: list[str] = [f"state_ok_for_{label.value}"]
            local_block: list[str] = []
            local_req: list[str] = []

            if trust < need_trust:
                local_block.append("trust_score")
                local_req.append(f"trust>={need_trust}")
                local_reasons.append("trust_below_policy")
                gap["failed"].append(f"trust<{need_trust}")
            if not _risk_ok(risk, max_risk):
                local_block.append("risk_level")
                local_req.append(f"risk<={max_risk}")
                local_reasons.append("risk_above_policy")
                gap["failed"].append(f"risk>{max_risk}")
            if ready_ok and (readiness is None or readiness not in ready_ok):
                local_block.append("readiness_label")
                local_req.append(f"readiness_in:{','.join(sorted(ready_ok))}")
                local_reasons.append("readiness_not_met")
                gap["failed"].append("readiness_not_met")
            if capacity < min_cap:
                local_block.append("daily_capacity")
                local_req.append(f"daily_capacity>={min_cap}")
                local_reasons.append("capacity_below_policy")
                gap["failed"].append(f"capacity<{min_cap}")
            if usage < min_usage or remaining < min_usage:
                local_block.append("budget")
                local_req.append(f"recommended_usage>={min_usage}")
                local_reasons.append("budget_below_policy")
                gap["failed"].append(f"budget<{min_usage}")

            if local_block:
                tier_gaps.append(gap)
                return None
            return EligibilityDecision(
                label.value,
                tuple(local_reasons + reasons),
                (),
                (),
                _NEXT.get(label, "reevaluate"),
                policy_version,
                DECISION_VERSION,
                policy_source=policy_source,
                closest_tier=label.value,
                tier_gaps=(),
            )

        for meta in _TIER_META:
            hit = evaluate_tier(*meta)
            if hit is not None:
                return hit

        # Closest = fewest failed conditions among evaluated tiers; prefer higher tier on tie
        closest = None
        if tier_gaps:
            closest = min(tier_gaps, key=lambda g: (len(g.get("failed") or []), -_tier_rank(g["tier"])))
        exact_req: list[str] = []
        if closest:
            exact_req.extend(closest.get("failed") or [])
            exact_req.append(f"closest_tier:{closest['tier']}")
            exact_req.append(f"required_trust>={closest['required_trust']}")
            exact_req.append(f"max_risk:{closest['max_risk']}")
            exact_req.append(f"readiness_in:{','.join(closest['required_readiness'])}")
            exact_req.append(f"daily_capacity>={closest['min_daily_capacity']}")
            exact_req.append(f"recommended_usage>={closest['min_recommended_usage']}")
        reasons.append("no_eligibility_tier_matched")
        return _deny(
            *reasons,
            blocking=("tier_requirements",),
            required=tuple(dict.fromkeys(exact_req or [
                "fleet_state_in_policy_eligible_set",
                "trust_meets_tier",
                "risk_within_tier",
                "readiness_meets_tier",
                "capacity_and_budget_meet_tier",
            ])),
            next_recommendation="improve_trust_risk_readiness_capacity_or_state",
            policy_version=policy_version,
            policy_source=policy_source,
            closest_tier=(closest or {}).get("tier"),
            tier_gaps=tuple(tier_gaps),
        )


def _tier_rank(label: str) -> int:
    order = {
        EligibilityLabel.ELIGIBLE_FOR_HIGH_VOLUME.value: 4,
        EligibilityLabel.ELIGIBLE_FOR_STANDARD_CAMPAIGN.value: 3,
        EligibilityLabel.ELIGIBLE_FOR_LIMITED_CAMPAIGN.value: 2,
        EligibilityLabel.ELIGIBLE_FOR_TRIAL.value: 1,
    }
    return order.get(label, 0)
