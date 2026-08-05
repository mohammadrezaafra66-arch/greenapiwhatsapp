"""V67 Phase 3 — Shadow comparison diagnostics (no repair)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.services.fleet_state import FleetState
from app.services.warmup_state import WarmupState


@dataclass(frozen=True)
class ShadowComparison:
    label: str  # MATCH | SAFE_MISMATCH | DANGEROUS_MISMATCH | INSUFFICIENT_EVIDENCE
    reasons: tuple[str, ...]
    details: dict[str, Any]


def compare_shadow(
    *,
    canonical: str | None,
    adapter_recommended: str | None,
    journey_recommended: str | None,
    account_status: str | None,
    warmup_state: str | None,
    live_state: str | None,
    incidents: list[str] | None,
    evidence_complete: bool = True,
) -> ShadowComparison:
    incidents = incidents or []
    reasons: list[str] = []
    live = (live_state or "").lower() if live_state else None

    if not evidence_complete:
        return ShadowComparison("INSUFFICIENT_EVIDENCE", ("evidence_incomplete",), {
            "canonical": canonical, "adapter": adapter_recommended, "journey": journey_recommended,
        })

    # Dangerous mismatches
    if warmup_state == WarmupState.GRADUATED.value and canonical == FleetState.WARMUP_READY.value:
        reasons.append("legacy_GRADUATED_vs_canonical_WARMUP_READY")
    if account_status == "active" and live == "suspended":
        reasons.append("account_active_but_live_suspended")
    if canonical in (
        FleetState.WARMUP_READY.value, FleetState.CAMPAIGN_READY.value, FleetState.MATURE.value,
    ) and any(i in ("suspended", "blocked", "forced_logout") for i in incidents):
        reasons.append("canonical_ready_with_unresolved_major_incident")
    if canonical in (FleetState.CAMPAIGN_READY.value, FleetState.MATURE.value):
        reasons.append("canonical_campaign_or_mature_unexpected_in_phase3")

    danger_keys = {
        "account_active_but_live_suspended",
        "canonical_ready_with_unresolved_major_incident",
        "canonical_campaign_or_mature_unexpected_in_phase3",
    }
    if any(r in danger_keys for r in reasons):
        return ShadowComparison("DANGEROUS_MISMATCH", tuple(reasons), {
            "canonical": canonical, "adapter": adapter_recommended, "journey": journey_recommended,
            "account_status": account_status, "warmup_state": warmup_state, "live": live,
            "incidents": incidents,
        })

    if reasons:
        # GRADUATED vs WARMUP_READY is expected SAFE after Phase 2 mapping
        return ShadowComparison("SAFE_MISMATCH", tuple(reasons), {
            "canonical": canonical, "adapter": adapter_recommended, "journey": journey_recommended,
            "warmup_state": warmup_state,
        })

    # Compare recommendations
    vals = {v for v in (canonical, adapter_recommended, journey_recommended) if v}
    if len(vals) <= 1:
        return ShadowComparison("MATCH", ("aligned",), {
            "canonical": canonical, "adapter": adapter_recommended, "journey": journey_recommended,
        })

    return ShadowComparison("SAFE_MISMATCH", ("recommendation_divergence",), {
        "canonical": canonical, "adapter": adapter_recommended, "journey": journey_recommended,
    })
