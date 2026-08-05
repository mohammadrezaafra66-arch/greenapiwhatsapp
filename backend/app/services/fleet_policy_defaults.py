"""V67 Phase 2 — CONSERVATIVE policy seed (D-H3). Storage only; no runtime activation."""
from __future__ import annotations

# Exact WarmupConfig ramp (bit-identical) — total inbound+outbound flow metric.
CONSERVATIVE_RAMP_CURVE = [12, 20, 32, 48, 66, 84, 100]

CONSERVATIVE_POLICY_SETTINGS: dict = {
    "flow_metric": "incoming_plus_outgoing",
    "flow_metric_note": (
        "12→100 is recommended total daily inbound+outbound flow; configurable; "
        "not a Green API hard guarantee"
    ),
    "ramp_curve": list(CONSERVATIVE_RAMP_CURVE),
    "total_flow_min": 12,
    "total_flow_max": 100,
    "maintenance_flow": 10,
    "allowed_states_placeholder": [
        "AUTHORIZED_QUIET", "INBOUND_BUILDING", "BIDIRECTIONAL_BUILDING",
        "CONTROLLED_RAMP", "WARMUP_READY", "GRADUATION_TRIAL",
        "CAMPAIGN_READY", "MATURE", "MAINTENANCE",
    ],
    "risk_thresholds_placeholder": {
        "yellowcard_to_at_risk": True,
        "repeat_yellowcard_to_rewarm": None,
    },
    "inactivity_thresholds_placeholder": {
        "keepwarm_days": 10,
        "erosion_days": 14,
        "logout_days": 30,
    },
    "graduation_requirements_placeholder": {
        "requires_graduation_trial": True,
        "day10_state": "WARMUP_READY",
        "no_auto_campaign_ready": True,
    },
    "scheduling_jitter_placeholder": {
        "enabled": True,
        "note": "Phase 2 stores only; scheduler not activated",
    },
    "breaker_references": {
        "fleet_suspend_window_hours": 24,
        "fleet_suspend_distinct_accounts": 2,
        "mesh_killswitch_hours": 48,
        "coexist": True,
    },
    "peers_min": 3,
    "peers_max": 6,
    # Phase 6 — CampaignEligibilityEngine thresholds (policy-driven; not hardcoded in engine)
    "eligibility_rules": {
        "blocked_fleet_states": [
            "NEW", "PRECHECK", "QR_WAITING", "READY_TO_LINK",
            "SUSPENDED", "BLOCKED", "FORCED_LOGOUT", "REWARM_REQUIRED",
            "FAILED", "RETIRED", "PAUSED",
        ],
        "trial_fleet_states": ["WARMUP_READY", "GRADUATION_TRIAL"],
        "limited_fleet_states": ["GRADUATION_TRIAL", "CAMPAIGN_READY"],
        "standard_fleet_states": ["CAMPAIGN_READY", "MATURE", "MAINTENANCE"],
        "high_volume_fleet_states": ["MATURE", "MAINTENANCE"],
        "trial_min_trust": 55,
        "limited_min_trust": 65,
        "standard_min_trust": 75,
        "high_volume_min_trust": 85,
        "trial_max_risk": "LOW",
        "limited_max_risk": "LOW",
        "standard_max_risk": "NORMAL",
        "high_volume_max_risk": "NORMAL",
        "require_readiness_for_trial": ["READY_FOR_TRIAL", "READY_FOR_CAMPAIGN", "READY_FOR_MATURE"],
        # Limited+ must NOT accept READY_FOR_TRIAL (Phase 6.1 monotonic readiness)
        "require_readiness_for_limited": ["READY_FOR_CAMPAIGN", "READY_FOR_MATURE"],
        "require_readiness_for_standard": ["READY_FOR_CAMPAIGN", "READY_FOR_MATURE"],
        # High volume fail-closed: READY_FOR_MATURE only until owner unlocks broader set
        "require_readiness_for_high_volume": ["READY_FOR_MATURE"],
        "min_daily_capacity_trial": 1,
        "min_daily_capacity_limited": 5,
        "min_daily_capacity_standard": 20,
        "min_daily_capacity_high_volume": 50,
        "min_recommended_usage_trial": 1,
        "min_recommended_usage_limited": 3,
        "min_recommended_usage_standard": 10,
        "min_recommended_usage_high_volume": 30,
        "min_incident_free_days": 3,
        "block_on_breaker": True,
        "block_on_open_major_incidents": True,
        "major_incident_types": [
            "suspended", "blocked", "forced_logout", "device_restriction",
        ],
        # Phase 6.1 — Journey fail-closed contract
        "journey_hard_block_statuses": ["PAUSED", "FAILED", "CANCELLED"],
        "journey_simulation_only_statuses": ["SIMULATING"],
        "journey_allowed_for_eligibility": ["ACTIVE"],
        "journey_missing_blocks": True,
        "journey_unknown_blocks": True,
        "unknown_fleet_state_blocks": True,
        "unknown_risk_blocks": True,
        "unknown_readiness_blocks": True,
    },
    # Phase 7 — Shadow sensor freshness (policy-driven; fail-closed if absent)
    "shadow_freshness": {
        "live_state_max_age_seconds": 90,
        "webhook_max_age_seconds": 3600,
        "incidents_max_age_seconds": 86400,
        "breaker_max_age_seconds": 300,
        "journey_max_age_seconds": 86400,
        "scoring_max_age_seconds": 3600,
        "capacity_max_age_seconds": 3600,
        "eligibility_max_age_seconds": 3600,
        "legacy_observation_max_age_seconds": 300,
        "policy_max_age_seconds": 86400,
        "critical_sensors": [
            "live_state", "policy", "breaker", "incidents", "eligibility",
        ],
        "dangerous_mismatch_threshold_status": "UNRATIFIED",
    },
}


def validate_policy_settings(settings: dict) -> tuple[bool, str]:
    if not isinstance(settings, dict):
        return False, "settings_must_be_object"
    curve = settings.get("ramp_curve")
    if curve is not None:
        if not isinstance(curve, list) or not all(isinstance(x, int) for x in curve):
            return False, "ramp_curve_must_be_int_list"
        if any(x < 0 for x in curve):
            return False, "ramp_curve_negative"
    metric = settings.get("flow_metric")
    if metric is not None and metric != "incoming_plus_outgoing":
        return False, "flow_metric_must_be_incoming_plus_outgoing"
    return True, "ok"
