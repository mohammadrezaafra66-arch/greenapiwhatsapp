"""V67 Phase 7 — pure ShadowComparisonEngine (no IO / send / mutation)."""
from __future__ import annotations
from typing import Any

from app.services.shadow_types import (
    ShadowComparisonResult, ShadowMismatchClass, ShadowSeverity,
    ShadowThresholdStatus, SHADOW_VERSION,
)

_BLOCKED = {
    "SUSPENDED", "BLOCKED", "FORCED_LOGOUT", "FAILED", "RETIRED", "PAUSED", "REWARM_REQUIRED",
}
_MAJOR = {"suspended", "blocked", "forced_logout", "device_restriction"}
_ELIGIBLE_TIERS = {
    "ELIGIBLE_FOR_TRIAL", "ELIGIBLE_FOR_LIMITED_CAMPAIGN",
    "ELIGIBLE_FOR_STANDARD_CAMPAIGN", "ELIGIBLE_FOR_HIGH_VOLUME",
}


def _legacy_allows(legacy_eligibility: str | None, legacy_ok: bool | None) -> bool | None:
    if legacy_ok is not None:
        return bool(legacy_ok)
    if not legacy_eligibility:
        return None
    s = legacy_eligibility.lower()
    if s in ("ok", "eligible", "allowed", "true"):
        return True
    if s.startswith("live_state:") or s in (
        "not_active", "cooldown", "throttled", "connect_cooldown",
        "fleet_breaker", "unresolved_critical_incident", "unknown_live_state",
    ):
        return False
    return None


class ShadowComparisonEngine:
    """Deterministic mismatch classification. Precedence per Phase 7 mission."""

    version = SHADOW_VERSION

    def compare(
        self,
        *,
        canonical_fleet_state: str | None = None,
        adapter_recommended_state: str | None = None,
        journey_recommended_state: str | None = None,
        trust_score: float | None = None,
        risk_level: str | None = None,
        readiness_label: str | None = None,
        daily_capacity: int | None = None,
        recommended_usage: int | None = None,
        eligibility_decision: str | None = None,
        legacy_account_status: str | None = None,
        legacy_warmup_state: str | None = None,
        legacy_eligibility: str | None = None,
        legacy_send_allowed: bool | None = None,
        live_state: str | None = None,
        incidents: list[str] | None = None,
        breaker_tripped: bool = False,
        sensor_freshness: dict[str, Any] | None = None,
        policy_version: int | None = None,
        expected_policy_version: int | None = None,
        evidence_complete: bool = True,
        runtime_unknown: bool = False,
        journey_status: str | None = None,
    ) -> ShadowComparisonResult:
        incidents = [str(i) for i in (incidents or [])]
        freshness = sensor_freshness or {}
        stale = tuple(sorted(k for k, v in freshness.items() if v in ("stale", "missing", "unknown")))
        reasons: list[str] = []
        missing: list[str] = []
        details: dict[str, Any] = {
            "canonical": canonical_fleet_state,
            "adapter": adapter_recommended_state,
            "journey_rec": journey_recommended_state,
            "eligibility": eligibility_decision,
            "legacy_eligibility": legacy_eligibility,
            "legacy_send_allowed": legacy_send_allowed,
            "live_state": live_state,
            "journey_status": journey_status,
            "dangerous_threshold_status": ShadowThresholdStatus.UNRATIFIED.value,
        }

        def result(
            cls: ShadowMismatchClass,
            sev: ShadowSeverity,
            *extra: str,
            legacy_more: bool = False,
            v67_more: bool = False,
            policy_mm: bool = False,
        ) -> ShadowComparisonResult:
            return ShadowComparisonResult(
                cls.value, sev.value,
                tuple(reasons + list(extra)) or (cls.value.lower(),),
                tuple(dict.fromkeys(missing)),
                stale,
                legacy_more, v67_more, policy_mm,
                details,
            )

        # 1. unknown runtime
        if runtime_unknown:
            reasons.append("runtime_unknown")
            missing.append("live_state")
            return result(ShadowMismatchClass.RUNTIME_UNKNOWN, ShadowSeverity.HIGH)
        if live_state is None:
            reasons.append("live_state_missing")
            missing.append("live_state")
            return result(ShadowMismatchClass.RUNTIME_UNKNOWN, ShadowSeverity.HIGH)
        if str(live_state).strip().lower() in ("", "unknown"):
            reasons.append("live_state_unknown")
            missing.append("live_state")
            return result(ShadowMismatchClass.RUNTIME_UNKNOWN, ShadowSeverity.HIGH)

        # 2. stale critical sensors
        critical_stale = [k for k in stale if k in (
            "live_state", "policy", "breaker", "incidents", "eligibility",
        )]
        if critical_stale or freshness.get("_fail_closed"):
            reasons.append("critical_sensor_stale")
            missing.extend(critical_stale)
            return result(ShadowMismatchClass.SENSOR_STALE, ShadowSeverity.HIGH)

        # 3. open major incident
        major_hit = [i for i in incidents if i in _MAJOR]
        if major_hit:
            reasons.append(f"open_major_incident:{','.join(sorted(major_hit))}")
            # If V67 eligibility still permits → dangerous / v67 more permissive
            if eligibility_decision in _ELIGIBLE_TIERS:
                return result(
                    ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.CRITICAL,
                    "v67_eligible_with_major_incident", v67_more=True,
                )
            return result(ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.HIGH)

        # 4. breaker
        if breaker_tripped:
            reasons.append("breaker_tripped")
            if eligibility_decision in _ELIGIBLE_TIERS:
                return result(
                    ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.CRITICAL,
                    "v67_eligible_with_breaker", v67_more=True,
                )
            return result(ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.HIGH)

        # 5. blocked/terminal FleetState
        if canonical_fleet_state in _BLOCKED:
            reasons.append(f"blocked_fleet_state:{canonical_fleet_state}")
            if eligibility_decision in _ELIGIBLE_TIERS:
                return result(
                    ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.CRITICAL,
                    "v67_eligible_in_blocked_state", v67_more=True,
                )
            return result(ShadowMismatchClass.SAFE_MISMATCH, ShadowSeverity.MEDIUM)

        # Journey fail-closed diagnostics (align Phase 6.1)
        if journey_status in ("FAILED", "CANCELLED", "PAUSED", "COMPLETED", "SIMULATING") or journey_status is None:
            if journey_status is None:
                missing.append("journey_status")
                reasons.append("journey_missing")
            else:
                reasons.append(f"journey_status:{journey_status}")
            if eligibility_decision in _ELIGIBLE_TIERS:
                return result(
                    ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.HIGH,
                    "eligibility_despite_journey_fail_closed", v67_more=True,
                )

        # High volume readiness check (D-P7-12 informational if present)
        if eligibility_decision == "ELIGIBLE_FOR_HIGH_VOLUME" and readiness_label != "READY_FOR_MATURE":
            reasons.append("high_volume_without_mature_readiness")
            return result(ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.CRITICAL)

        # 8. policy version mismatch
        if (
            expected_policy_version is not None
            and policy_version is not None
            and int(expected_policy_version) != int(policy_version)
        ):
            reasons.append("policy_version_mismatch")
            return result(
                ShadowMismatchClass.POLICY_VERSION_MISMATCH, ShadowSeverity.MEDIUM,
                policy_mm=True,
            )

        # 9. insufficient evidence
        if not evidence_complete:
            reasons.append("evidence_incomplete")
            missing.append("evidence")
            return result(ShadowMismatchClass.INSUFFICIENT_EVIDENCE, ShadowSeverity.MEDIUM)

        legacy_ok = _legacy_allows(legacy_eligibility, legacy_send_allowed)
        v67_ok = eligibility_decision in _ELIGIBLE_TIERS

        # 6. legacy more permissive than fail-closed V67
        if legacy_ok is True and not v67_ok:
            reasons.append("legacy_allows_v67_blocks")
            return result(
                ShadowMismatchClass.LEGACY_MORE_PERMISSIVE, ShadowSeverity.HIGH,
                legacy_more=True,
            )

        # 7. V67 more permissive than legacy
        if legacy_ok is False and v67_ok:
            reasons.append("v67_allows_legacy_blocks")
            return result(
                ShadowMismatchClass.V67_MORE_PERMISSIVE, ShadowSeverity.CRITICAL,
                "dangerous_without_numeric_threshold", v67_more=True,
            )

        # active + live suspended
        if (legacy_account_status or "").lower() == "active" and (live_state or "").lower() == "suspended":
            reasons.append("account_active_but_live_suspended")
            return result(ShadowMismatchClass.DANGEROUS_MISMATCH, ShadowSeverity.CRITICAL)

        # recommendation divergence (safe)
        vals = {v for v in (canonical_fleet_state, adapter_recommended_state, journey_recommended_state) if v}
        if len(vals) > 1:
            reasons.append("recommendation_divergence")
            return result(ShadowMismatchClass.SAFE_MISMATCH, ShadowSeverity.LOW)

        if legacy_warmup_state == "GRADUATED" and canonical_fleet_state == "WARMUP_READY":
            reasons.append("legacy_GRADUATED_vs_canonical_WARMUP_READY")
            return result(ShadowMismatchClass.SAFE_MISMATCH, ShadowSeverity.INFO)

        if legacy_ok is None and eligibility_decision:
            reasons.append("legacy_eligibility_unknown")
            missing.append("legacy_eligibility")
            return result(ShadowMismatchClass.INSUFFICIENT_EVIDENCE, ShadowSeverity.LOW)

        reasons.append("aligned")
        return result(ShadowMismatchClass.MATCH, ShadowSeverity.INFO)
