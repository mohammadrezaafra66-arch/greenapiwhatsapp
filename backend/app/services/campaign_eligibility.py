"""V67 Phase 6 — Campaign Eligibility Engine (decisions only; never executes)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS, validate_policy_settings

DECISION_VERSION = "v67.6.eligibility.1"

EligibilityLabel = str
# NOT_ELIGIBLE | ELIGIBLE_FOR_TRIAL | ELIGIBLE_FOR_LIMITED_CAMPAIGN |
# ELIGIBLE_FOR_STANDARD_CAMPAIGN | ELIGIBLE_FOR_HIGH_VOLUME

_RISK_ORDER = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

_LEVELS = (
    "ELIGIBLE_FOR_HIGH_VOLUME",
    "ELIGIBLE_FOR_STANDARD_CAMPAIGN",
    "ELIGIBLE_FOR_LIMITED_CAMPAIGN",
    "ELIGIBLE_FOR_TRIAL",
)


@dataclass(frozen=True)
class EligibilityDecision:
    decision: EligibilityLabel
    reason_codes: tuple[str, ...]
    blocking_evidence: tuple[str, ...]
    required_evidence: tuple[str, ...]
    next_recommendation: str
    policy_version: int | None
    decision_version: str
    simulation_only: bool = True
    mutates_runtime: bool = False
    executes: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason_codes"] = list(self.reason_codes)
        d["blocking_evidence"] = list(self.blocking_evidence)
        d["required_evidence"] = list(self.required_evidence)
        return d


def _settings(policy: dict | None) -> dict:
    policy = policy or {}
    return policy.get("settings_json") or policy.get("settings") or policy


def _rules(settings: dict) -> dict:
    rules = settings.get("eligibility_rules")
    if isinstance(rules, dict) and rules:
        return dict(rules)
    # Fall back to conservative defaults (still policy-sourced, not engine-hardcoded)
    return dict(CONSERVATIVE_POLICY_SETTINGS.get("eligibility_rules") or {})


def _risk_ok(level: str, max_level: str) -> bool:
    return _RISK_ORDER.get(level, 99) <= _RISK_ORDER.get(max_level, 0)


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
    ) -> EligibilityDecision:
        evidence = evidence or {}
        incidents = [str(i) for i in (incidents or []) if i]
        for i in evidence.get("incidents") or []:
            if i and str(i) not in incidents:
                incidents.append(str(i))

        settings = _settings(policy)
        ok, msg = validate_policy_settings(settings if isinstance(settings, dict) else {})
        if not ok:
            return EligibilityDecision(
                "NOT_ELIGIBLE",
                (f"policy_invalid:{msg}",),
                ("valid_policy",),
                ("valid_policy",),
                "fix_or_provide_valid_policy",
                policy_version,
                self.version,
            )

        rules = _rules(settings)
        if not rules:
            return EligibilityDecision(
                "NOT_ELIGIBLE",
                ("eligibility_rules_missing",),
                ("eligibility_rules",),
                ("eligibility_rules",),
                "add_eligibility_rules_to_policy",
                policy_version,
                self.version,
            )

        reasons: list[str] = []
        blocking: list[str] = []
        required: list[str] = []
        state = (fleet_state or "").strip()
        trust = float(trust_score or 0)
        risk = str(risk_level or "CRITICAL")
        readiness = (readiness_label or "").strip() or None
        capacity = int(daily_capacity or 0)
        usage = int(recommended_usage if recommended_usage is not None else 0)
        remaining = int(remaining_budget) if remaining_budget is not None else usage
        ifree = evidence.get("incident_free_days")

        # Hard blocks from policy
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

        if journey_status in ("FAILED", "CANCELLED"):
            blocking.append("journey_status")
            reasons.append(f"journey_status:{journey_status}")

        if blocking:
            return EligibilityDecision(
                "NOT_ELIGIBLE",
                tuple(reasons) or ("blocked",),
                tuple(dict.fromkeys(blocking)),
                tuple(dict.fromkeys(required + [
                    "healthy_fleet_state", "clear_breaker", "no_major_incidents",
                ])),
                "resolve_blocks_then_reevaluate",
                policy_version,
                self.version,
            )

        def try_level(
            label: str,
            states_key: str,
            trust_key: str,
            risk_key: str,
            readiness_key: str,
            cap_key: str,
            usage_key: str,
        ) -> EligibilityDecision | None:
            states = set(rules.get(states_key) or [])
            if state not in states:
                return None
            need_trust = float(rules.get(trust_key) or 0)
            max_risk = str(rules.get(risk_key) or "NORMAL")
            ready_ok = set(rules.get(readiness_key) or [])
            min_cap = int(rules.get(cap_key) or 0)
            min_usage = int(rules.get(usage_key) or 0)
            local_reasons: list[str] = [f"state_ok_for_{label}"]
            local_block: list[str] = []
            local_req: list[str] = []

            if trust < need_trust:
                local_block.append("trust_score")
                local_req.append(f"trust>={need_trust}")
                local_reasons.append("trust_below_policy")
            if not _risk_ok(risk, max_risk):
                local_block.append("risk_level")
                local_req.append(f"risk<={max_risk}")
                local_reasons.append("risk_above_policy")
            if ready_ok and (readiness is None or readiness not in ready_ok):
                local_block.append("readiness_label")
                local_req.append(f"readiness_in:{','.join(sorted(ready_ok))}")
                local_reasons.append("readiness_not_met")
            if capacity < min_cap:
                local_block.append("daily_capacity")
                local_req.append(f"daily_capacity>={min_cap}")
                local_reasons.append("capacity_below_policy")
            if usage < min_usage or remaining < min_usage:
                local_block.append("budget")
                local_req.append(f"recommended_usage>={min_usage}")
                local_reasons.append("budget_below_policy")

            if local_block:
                return None  # try lower tier
            return EligibilityDecision(
                label,
                tuple(local_reasons + reasons),
                (),
                (),
                {
                    "ELIGIBLE_FOR_HIGH_VOLUME": "simulate_high_volume_plan_only",
                    "ELIGIBLE_FOR_STANDARD_CAMPAIGN": "simulate_standard_campaign_plan_only",
                    "ELIGIBLE_FOR_LIMITED_CAMPAIGN": "simulate_limited_campaign_plan_only",
                    "ELIGIBLE_FOR_TRIAL": "simulate_graduation_trial_only",
                }.get(label, "reevaluate"),
                policy_version,
                self.version,
            )

        # Highest tier first
        for label, sk, tk, rk, rdk, ck, uk in (
            ("ELIGIBLE_FOR_HIGH_VOLUME", "high_volume_fleet_states", "high_volume_min_trust",
             "high_volume_max_risk", "require_readiness_for_high_volume",
             "min_daily_capacity_high_volume", "min_recommended_usage_high_volume"),
            ("ELIGIBLE_FOR_STANDARD_CAMPAIGN", "standard_fleet_states", "standard_min_trust",
             "standard_max_risk", "require_readiness_for_standard",
             "min_daily_capacity_standard", "min_recommended_usage_standard"),
            ("ELIGIBLE_FOR_LIMITED_CAMPAIGN", "limited_fleet_states", "limited_min_trust",
             "limited_max_risk", "require_readiness_for_limited",
             "min_daily_capacity_limited", "min_recommended_usage_limited"),
            ("ELIGIBLE_FOR_TRIAL", "trial_fleet_states", "trial_min_trust",
             "trial_max_risk", "require_readiness_for_trial",
             "min_daily_capacity_trial", "min_recommended_usage_trial"),
        ):
            hit = try_level(label, sk, tk, rk, rdk, ck, uk)
            if hit is not None:
                return hit

        # Did not meet any tier — explain closest gaps
        required.extend([
            "fleet_state_in_policy_eligible_set",
            "trust_meets_tier",
            "risk_within_tier",
            "readiness_meets_tier",
            "capacity_and_budget_meet_tier",
        ])
        reasons.append("no_eligibility_tier_matched")
        return EligibilityDecision(
            "NOT_ELIGIBLE",
            tuple(reasons),
            ("tier_requirements",),
            tuple(dict.fromkeys(required)),
            "improve_trust_risk_readiness_capacity_or_state",
            policy_version,
            self.version,
        )
