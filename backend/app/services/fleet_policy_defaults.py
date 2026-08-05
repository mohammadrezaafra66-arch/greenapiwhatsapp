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
