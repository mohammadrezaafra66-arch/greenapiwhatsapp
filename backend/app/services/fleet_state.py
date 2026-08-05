"""V67 Phase 2 — Canonical FleetState enum (matches docs/v67/07-fleet-state-matrix.md)."""
from __future__ import annotations
import enum


class FleetState(str, enum.Enum):
    NEW = "NEW"
    PRECHECK = "PRECHECK"
    QR_WAITING = "QR_WAITING"
    READY_TO_LINK = "READY_TO_LINK"
    AUTHORIZED_QUIET = "AUTHORIZED_QUIET"
    INBOUND_BUILDING = "INBOUND_BUILDING"
    BIDIRECTIONAL_BUILDING = "BIDIRECTIONAL_BUILDING"
    CONTROLLED_RAMP = "CONTROLLED_RAMP"
    WARMUP_READY = "WARMUP_READY"
    GRADUATION_TRIAL = "GRADUATION_TRIAL"
    CAMPAIGN_READY = "CAMPAIGN_READY"
    MATURE = "MATURE"
    MAINTENANCE = "MAINTENANCE"
    AT_RISK = "AT_RISK"
    PAUSED = "PAUSED"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"
    FORCED_LOGOUT = "FORCED_LOGOUT"
    RECOVERY_COOLDOWN = "RECOVERY_COOLDOWN"
    REWARM_REQUIRED = "REWARM_REQUIRED"
    FAILED = "FAILED"
    RETIRED = "RETIRED"


FLEET_STATE_VALUES: tuple[str, ...] = tuple(s.value for s in FleetState)

# Risk budget overlay (not a FleetState) — stored on fleet_accounts.risk_budget
class RiskBudget(str, enum.Enum):
    NORMAL = "NORMAL"
    SLOW = "SLOW"
    RECEIVE_ONLY = "RECEIVE_ONLY"
    PAUSED = "PAUSED"
    REWARM_REQUIRED = "REWARM_REQUIRED"


# States that must never be granted by automatic Phase 2 seed
SEED_FORBIDDEN_AUTO_STATES = frozenset({
    FleetState.CAMPAIGN_READY.value,
    FleetState.MATURE.value,
    FleetState.MAINTENANCE.value,
    FleetState.GRADUATION_TRIAL.value,
})
