"""V67 Phase 6.1 — eligibility_rules schema validation (fail-closed)."""
from __future__ import annotations
from typing import Any

from app.services.fleet_state import FLEET_STATE_VALUES
from app.services.journey_types import JourneyStatus

VALID_RISK = frozenset({"NORMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"})
VALID_READINESS = frozenset({
    "NOT_READY", "READY_FOR_TRIAL", "READY_FOR_CAMPAIGN", "READY_FOR_MATURE",
})
VALID_JOURNEY = frozenset(s.value for s in JourneyStatus)
FLEET_SET = frozenset(FLEET_STATE_VALUES)

_RISK_ORDER = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_READINESS_RANK = {
    "NOT_READY": 0,
    "READY_FOR_TRIAL": 1,
    "READY_FOR_CAMPAIGN": 2,
    "READY_FOR_MATURE": 3,
}

REQUIRED_KEYS = (
    "blocked_fleet_states",
    "trial_fleet_states",
    "limited_fleet_states",
    "standard_fleet_states",
    "high_volume_fleet_states",
    "trial_min_trust",
    "limited_min_trust",
    "standard_min_trust",
    "high_volume_min_trust",
    "trial_max_risk",
    "limited_max_risk",
    "standard_max_risk",
    "high_volume_max_risk",
    "require_readiness_for_trial",
    "require_readiness_for_limited",
    "require_readiness_for_standard",
    "require_readiness_for_high_volume",
    "min_daily_capacity_trial",
    "min_daily_capacity_limited",
    "min_daily_capacity_standard",
    "min_daily_capacity_high_volume",
    "min_recommended_usage_trial",
    "min_recommended_usage_limited",
    "min_recommended_usage_standard",
    "min_recommended_usage_high_volume",
    "min_incident_free_days",
    "block_on_breaker",
    "block_on_open_major_incidents",
    "major_incident_types",
    "journey_hard_block_statuses",
    "journey_simulation_only_statuses",
    "journey_allowed_for_eligibility",
    "journey_missing_blocks",
    "journey_unknown_blocks",
    "unknown_fleet_state_blocks",
    "unknown_risk_blocks",
    "unknown_readiness_blocks",
)

_LIST_FLEET_KEYS = (
    "blocked_fleet_states",
    "trial_fleet_states",
    "limited_fleet_states",
    "standard_fleet_states",
    "high_volume_fleet_states",
)
_LIST_READINESS_KEYS = (
    "require_readiness_for_trial",
    "require_readiness_for_limited",
    "require_readiness_for_standard",
    "require_readiness_for_high_volume",
)
_LIST_JOURNEY_KEYS = (
    "journey_hard_block_statuses",
    "journey_simulation_only_statuses",
    "journey_allowed_for_eligibility",
)
_TRUST_KEYS = (
    "trial_min_trust", "limited_min_trust", "standard_min_trust", "high_volume_min_trust",
)
_CAP_KEYS = (
    "min_daily_capacity_trial", "min_daily_capacity_limited",
    "min_daily_capacity_standard", "min_daily_capacity_high_volume",
)
_USAGE_KEYS = (
    "min_recommended_usage_trial", "min_recommended_usage_limited",
    "min_recommended_usage_standard", "min_recommended_usage_high_volume",
)
_RISK_KEYS = (
    "trial_max_risk", "limited_max_risk", "standard_max_risk", "high_volume_max_risk",
)
_BOOL_KEYS = (
    "block_on_breaker", "block_on_open_major_incidents",
    "journey_missing_blocks", "journey_unknown_blocks",
    "unknown_fleet_state_blocks", "unknown_risk_blocks", "unknown_readiness_blocks",
)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_eligibility_rules(rules: Any) -> tuple[bool, str]:
    """Fail-closed schema + monotonicity check for eligibility_rules."""
    if rules is None:
        return False, "eligibility_rules_missing"
    if not isinstance(rules, dict):
        return False, "eligibility_rules_must_be_object"
    if not rules:
        return False, "eligibility_rules_empty"

    for key in REQUIRED_KEYS:
        if key not in rules:
            return False, f"eligibility_rules_missing_key:{key}"

    for key in _LIST_FLEET_KEYS:
        val = rules[key]
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            return False, f"eligibility_rules_invalid_list:{key}"
        for x in val:
            if x not in FLEET_SET:
                return False, f"eligibility_rules_invalid_fleet_state:{key}:{x}"

    for key in _LIST_READINESS_KEYS:
        val = rules[key]
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            return False, f"eligibility_rules_invalid_list:{key}"
        for x in val:
            if x not in VALID_READINESS:
                return False, f"eligibility_rules_invalid_readiness:{key}:{x}"

    for key in _LIST_JOURNEY_KEYS:
        val = rules[key]
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            return False, f"eligibility_rules_invalid_list:{key}"
        for x in val:
            if x not in VALID_JOURNEY:
                return False, f"eligibility_rules_invalid_journey:{key}:{x}"

    for key in _TRUST_KEYS:
        v = rules[key]
        if not _is_num(v) or float(v) < 0 or float(v) > 100:
            return False, f"eligibility_rules_invalid_trust:{key}"

    for key in _CAP_KEYS + _USAGE_KEYS:
        v = rules[key]
        if not _is_num(v) or float(v) < 0:
            return False, f"eligibility_rules_invalid_nonnegative:{key}"

    v = rules["min_incident_free_days"]
    if not _is_num(v) or float(v) < 0:
        return False, "eligibility_rules_invalid_incident_free_days"

    for key in _RISK_KEYS:
        r = rules[key]
        if not isinstance(r, str) or r not in VALID_RISK:
            return False, f"eligibility_rules_invalid_risk:{key}"

    for key in _BOOL_KEYS:
        if not isinstance(rules[key], bool):
            return False, f"eligibility_rules_invalid_bool:{key}"

    majors = rules["major_incident_types"]
    if not isinstance(majors, list) or not all(isinstance(x, str) and x for x in majors):
        return False, "eligibility_rules_invalid_major_incidents"

    # Blocked states must not appear in eligible sets
    blocked = set(rules["blocked_fleet_states"])
    for key in (
        "trial_fleet_states", "limited_fleet_states",
        "standard_fleet_states", "high_volume_fleet_states",
    ):
        overlap = blocked.intersection(rules[key])
        if overlap:
            return False, f"eligibility_rules_blocked_overlap:{key}:{','.join(sorted(overlap))}"

    # Trust monotonicity: trial <= limited <= standard <= high_volume
    trusts = [
        float(rules["trial_min_trust"]),
        float(rules["limited_min_trust"]),
        float(rules["standard_min_trust"]),
        float(rules["high_volume_min_trust"]),
    ]
    if trusts != sorted(trusts):
        return False, "eligibility_rules_trust_not_monotonic"

    caps = [
        float(rules["min_daily_capacity_trial"]),
        float(rules["min_daily_capacity_limited"]),
        float(rules["min_daily_capacity_standard"]),
        float(rules["min_daily_capacity_high_volume"]),
    ]
    if caps != sorted(caps):
        return False, "eligibility_rules_capacity_not_monotonic"

    usages = [
        float(rules["min_recommended_usage_trial"]),
        float(rules["min_recommended_usage_limited"]),
        float(rules["min_recommended_usage_standard"]),
        float(rules["min_recommended_usage_high_volume"]),
    ]
    if usages != sorted(usages):
        return False, "eligibility_rules_usage_not_monotonic"

    # Risk max: higher tiers must not be more permissive (higher max risk ordinal)
    risk_maxes = [
        _RISK_ORDER[rules["trial_max_risk"]],
        _RISK_ORDER[rules["limited_max_risk"]],
        _RISK_ORDER[rules["standard_max_risk"]],
        _RISK_ORDER[rules["high_volume_max_risk"]],
    ]
    # Higher tier should have max_risk ordinal <= lower tier (stricter or equal)
    # trial may be most permissive (highest ordinal allowed). So descending or equal:
    if not (risk_maxes[0] >= risk_maxes[1] >= risk_maxes[2] >= risk_maxes[3]):
        return False, "eligibility_rules_risk_not_monotonic"

    # Readiness: min rank in each tier list must be non-decreasing across tiers
    def min_ready_rank(key: str) -> int:
        labels = rules[key]
        if not labels:
            return 99
        return min(_READINESS_RANK[x] for x in labels)

    ranks = [
        min_ready_rank("require_readiness_for_trial"),
        min_ready_rank("require_readiness_for_limited"),
        min_ready_rank("require_readiness_for_standard"),
        min_ready_rank("require_readiness_for_high_volume"),
    ]
    if ranks != sorted(ranks):
        return False, "eligibility_rules_readiness_not_monotonic"

    # Limited+ must not accept READY_FOR_TRIAL as sole unlock (no trial-only in higher tiers)
    for key in (
        "require_readiness_for_limited",
        "require_readiness_for_standard",
        "require_readiness_for_high_volume",
    ):
        if "READY_FOR_TRIAL" in rules[key]:
            return False, f"eligibility_rules_trial_readiness_in_higher_tier:{key}"

    # High volume fail-closed: must require READY_FOR_MATURE (may also allow only that)
    hv = set(rules["require_readiness_for_high_volume"])
    if hv != {"READY_FOR_MATURE"} and "READY_FOR_MATURE" not in hv:
        return False, "eligibility_rules_high_volume_requires_mature_readiness"
    if hv - {"READY_FOR_MATURE"}:
        # permissive extras forbidden until owner unlocks
        return False, "eligibility_rules_high_volume_readiness_not_fail_closed"

    return True, "ok"
