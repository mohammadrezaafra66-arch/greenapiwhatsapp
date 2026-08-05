"""V67 Phase 3/4 — Trust / Risk / Capacity ports.

Phase 4: TrustEngine + RiskEngine are real deterministic implementations.
CapacityPlanner remains a stub until a later phase.
"""
from __future__ import annotations
from typing import Protocol, Any

from app.services.trust_engine import TrustEngine
from app.services.risk_engine import RiskEngine


class TrustEnginePort(Protocol):
    def score(self, evidence: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        ...


class RiskEnginePort(Protocol):
    def assess(self, evidence: dict[str, Any], incidents: list[str], policy: dict[str, Any]) -> dict[str, Any]:
        ...


class CapacityPlannerPort(Protocol):
    def plan(self, fleet_state: str, policy: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        """Deferred — not implemented in Phase 4."""
        ...


# Back-compat names used by Phase 3 orchestrator
class StubTrustEngine(TrustEngine):
    """Phase 4: real TrustEngine (name kept for orchestrator imports)."""


class StubRiskEngine(RiskEngine):
    """Phase 4: real RiskEngine (name kept for orchestrator imports)."""


class StubCapacityPlanner:
    def plan(self, fleet_state: str, policy: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        return {"implemented": False, "phase": 4, "capacity": None, "deferred": True}
