"""V67 Phase 7 — policy-driven sensor freshness (fail-closed)."""
from __future__ import annotations
from datetime import datetime
from typing import Any


DEFAULT_SHADOW_FRESHNESS = {
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
}


def _freshness_policy(policy: dict | None) -> dict | None:
    policy = policy or {}
    settings = policy.get("settings_json") or policy.get("settings") or policy
    if not isinstance(settings, dict):
        return None
    rules = settings.get("shadow_freshness")
    if not isinstance(rules, dict) or not rules:
        # Fail closed — do not silently embed defaults for incomplete DB policies
        return None
    return dict(rules)


def evaluate_freshness(
    *,
    now: datetime,
    sensor_timestamps: dict[str, datetime | None],
    policy: dict | None,
) -> dict[str, Any]:
    """Return map sensor -> fresh|stale|missing|unknown plus _fail_closed flag."""
    rules = _freshness_policy(policy)
    out: dict[str, Any] = {}
    if rules is None:
        out["_fail_closed"] = True
        out["_reason"] = "shadow_freshness_policy_missing"
        for k in sensor_timestamps:
            out[k] = "unknown"
        return out

    out["_fail_closed"] = False
    for name, ts in sensor_timestamps.items():
        key = f"{name}_max_age_seconds"
        max_age = rules.get(key)
        if max_age is None:
            # generic fallback key pattern
            max_age = rules.get("default_max_age_seconds")
        if max_age is None:
            out[name] = "unknown"
            out["_fail_closed"] = True
            out["_reason"] = f"freshness_window_missing:{name}"
            continue
        if ts is None:
            out[name] = "missing"
            if name in (rules.get("critical_sensors") or DEFAULT_SHADOW_FRESHNESS["critical_sensors"]):
                out["_fail_closed"] = True
            continue
        if not isinstance(ts, datetime):
            out[name] = "unknown"
            out["_fail_closed"] = True
            continue
        age = (now - ts).total_seconds()
        out[name] = "fresh" if age <= float(max_age) else "stale"
        if out[name] == "stale" and name in (rules.get("critical_sensors") or []):
            out["_fail_closed"] = True
    return out
