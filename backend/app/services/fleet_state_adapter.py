"""V67 Phase 2 — FleetStateAdapter: sensors → recommended canonical state.

Does not execute journeys, send messages, or mutate Green API settings.
Does not change send_gate eligibility (runtime authority remains Phase 1 gate).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.account import AccountStatus
from app.services.fleet_state import FleetState, SEED_FORBIDDEN_AUTO_STATES
from app.services.warmup_state import WarmupState


CRITICAL_INCIDENT_TYPES = frozenset({
    "suspended", "blocked", "forced_logout", "notAuthorized",
    "device_restriction", "auth_churn", "yellowCard",
})

MAJOR_REWARM_INCIDENT_TYPES = frozenset({
    "suspended", "blocked", "forced_logout", "device_restriction",
})


@dataclass
class SensorSnapshot:
    account_status: str | None = None
    warmup_state: str | None = None
    live_state: str | None = None
    open_incidents: list[str] = field(default_factory=list)
    fleet_breaker_tripped: bool = False
    days_active: int | None = None
    has_real_inbound: bool = False
    has_real_outbound: bool = False
    recovery_mode: bool = False  # recovery Path B enrollment if known


@dataclass
class DeriveResult:
    recommended: str
    reason: str
    sensors: dict[str, Any]
    mismatches: list[str] = field(default_factory=list)


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    s = str(value).strip()
    return s or None


def _live_lower(live: str | None) -> str | None:
    return live.lower() if live else None


class FleetStateAdapter:
    """Canonical derivation per docs/v67/07-fleet-state-matrix.md §2."""

    def derive(self, sensors: SensorSnapshot, *, for_seed: bool = True) -> DeriveResult:
        status = _norm(sensors.account_status)
        warmup = _norm(sensors.warmup_state)
        live = _live_lower(_norm(sensors.live_state))
        incidents = [(_norm(i) or "") for i in sensors.open_incidents]
        incidents = [i for i in incidents if i]

        sensor_dict = {
            "account_status": status,
            "warmup_state": warmup,
            "live_state": live,
            "open_incidents": incidents,
            "fleet_breaker_tripped": sensors.fleet_breaker_tripped,
            "days_active": sensors.days_active,
            "has_real_inbound": sensors.has_real_inbound,
            "has_real_outbound": sensors.has_real_outbound,
            "recovery_mode": sensors.recovery_mode,
        }

        # 1. Terminal ops
        if status in (AccountStatus.deleted.value, AccountStatus.green_api_deleted.value):
            return DeriveResult(FleetState.RETIRED.value, "terminal_account_status", sensor_dict)

        # 2. Live danger
        if live == "blocked" or status == AccountStatus.banned.value or "blocked" in incidents:
            return DeriveResult(FleetState.BLOCKED.value, "blocked_sensor", sensor_dict)
        if live == "suspended" or status == AccountStatus.suspended.value or "suspended" in incidents:
            return DeriveResult(FleetState.SUSPENDED.value, "suspended_sensor", sensor_dict)
        if "forced_logout" in incidents or "device_restriction" in incidents:
            return DeriveResult(FleetState.FORCED_LOGOUT.value, "forced_logout_or_device", sensor_dict)
        if status == AccountStatus.disconnected.value and (
            live == "notauthorized" or "notAuthorized" in incidents or "notauthorized" in [i.lower() for i in incidents]
        ):
            return DeriveResult(FleetState.FORCED_LOGOUT.value, "disconnected_not_authorized", sensor_dict)

        # Major incident types still open → observable danger / rewarm path (seed never skips)
        if any(i in MAJOR_REWARM_INCIDENT_TYPES for i in incidents):
            # Prefer observable incident state already handled; residual → REWARM_REQUIRED
            if "suspended" in incidents:
                return DeriveResult(FleetState.SUSPENDED.value, "open_suspended_incident", sensor_dict)
            if "blocked" in incidents:
                return DeriveResult(FleetState.BLOCKED.value, "open_blocked_incident", sensor_dict)
            return DeriveResult(FleetState.REWARM_REQUIRED.value, "major_incident_rewarm", sensor_dict)

        # 4. Open critical (yellowCard / auth_churn)
        if "yellowCard" in incidents or "yellowcard" in [i.lower() for i in incidents]:
            return DeriveResult(FleetState.AT_RISK.value, "open_yellowcard", sensor_dict)
        if "auth_churn" in incidents:
            return DeriveResult(FleetState.AT_RISK.value, "auth_churn", sensor_dict)

        if sensors.fleet_breaker_tripped:
            return DeriveResult(FleetState.PAUSED.value, "fleet_breaker", sensor_dict)

        # Pending / not linked
        if status in (None, AccountStatus.pending.value) or live in ("notauthorized", None):
            if status == AccountStatus.pending.value and live in (None, "notauthorized"):
                return DeriveResult(FleetState.PRECHECK.value, "pending_or_unknown_live", sensor_dict)

        # Active path — legacy WarmupState as sensor only
        recommended, reason = self._map_warmup_progress(warmup, sensors)
        if for_seed and recommended in SEED_FORBIDDEN_AUTO_STATES:
            # Phase 2 seed: never auto CAMPAIGN_READY / MATURE / …
            recommended = FleetState.WARMUP_READY.value
            reason = f"{reason}_seed_capped_warmup_ready"

        mismatches = self.diagnose_mismatches(
            recommended, status=status, warmup=warmup, live=live,
        )
        return DeriveResult(recommended, reason, sensor_dict, mismatches)

    def _map_warmup_progress(self, warmup: str | None, sensors: SensorSnapshot) -> tuple[str, str]:
        if warmup == WarmupState.BLOCKED_RESET.value:
            return FleetState.REWARM_REQUIRED.value, "legacy_blocked_reset"
        if warmup == WarmupState.PAUSED.value:
            return FleetState.PAUSED.value, "legacy_paused"
        if warmup == WarmupState.YELLOWCARD.value:
            return FleetState.AT_RISK.value, "legacy_yellowcard"
        if warmup == WarmupState.GRADUATED.value:
            # D-H2 / Phase 2 seed: historical GRADUATED → WARMUP_READY only (never auto campaign)
            # Recovery GRADUATED and day-10-ish MATURING also stay non-campaign.
            return FleetState.WARMUP_READY.value, "legacy_graduated_to_warmup_ready"
        if warmup == WarmupState.MATURING.value:
            return FleetState.WARMUP_READY.value, "legacy_maturing_day10_warmup_ready"
        if warmup == WarmupState.RAMPING.value:
            return FleetState.CONTROLLED_RAMP.value, "legacy_ramping"
        if warmup == WarmupState.REPLYING.value:
            return FleetState.BIDIRECTIONAL_BUILDING.value, "legacy_replying"
        if warmup == WarmupState.RECEIVING.value:
            return FleetState.INBOUND_BUILDING.value, "legacy_receiving"
        if warmup in (WarmupState.COOLDOWN.value, WarmupState.ENROLLED.value):
            return FleetState.AUTHORIZED_QUIET.value, "legacy_enrolled_or_cooldown"

        # No enrollment — conservative
        if sensors.has_real_inbound and sensors.has_real_outbound:
            return FleetState.BIDIRECTIONAL_BUILDING.value, "activity_bidirectional_conservative"
        if sensors.has_real_inbound:
            return FleetState.INBOUND_BUILDING.value, "activity_inbound_only"
        status = _norm(sensors.account_status)
        if status == AccountStatus.active.value:
            return FleetState.AUTHORIZED_QUIET.value, "active_ambiguous_quiet"
        return FleetState.PRECHECK.value, "ambiguous_precheck"

    def diagnose_mismatches(
        self,
        canonical: str,
        *,
        status: str | None,
        warmup: str | None,
        live: str | None,
    ) -> list[str]:
        notes: list[str] = []
        if warmup == WarmupState.GRADUATED.value and canonical == FleetState.WARMUP_READY.value:
            notes.append("legacy_GRADUATED_mapped_to_WARMUP_READY_not_CAMPAIGN_READY")
        if warmup == WarmupState.MATURING.value and canonical == FleetState.WARMUP_READY.value:
            notes.append("legacy_MATURING_day10_is_WARMUP_READY_not_campaign")
        if status == AccountStatus.active.value and live == "suspended":
            notes.append("account_active_but_live_suspended")
        if canonical in (
            FleetState.CAMPAIGN_READY.value, FleetState.MATURE.value,
        ):
            notes.append("campaign_or_mature_requires_explicit_later_phase")
        return notes

    def rewarm_required_after_major(self, incident_type: str) -> str:
        """Immediate observable state for major incidents; path ends at REWARM_REQUIRED."""
        t = (incident_type or "").strip()
        if t == "suspended":
            return FleetState.SUSPENDED.value
        if t == "blocked":
            return FleetState.BLOCKED.value
        if t in ("forced_logout", "device_restriction"):
            return FleetState.FORCED_LOGOUT.value
        return FleetState.REWARM_REQUIRED.value
