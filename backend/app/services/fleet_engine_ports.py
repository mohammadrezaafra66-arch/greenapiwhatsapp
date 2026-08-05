"""V67 Phase 3 — Trust / Risk / Capacity interfaces only (no scoring)."""
from __future__ import annotations
from typing import Protocol, Any


class TrustEnginePort(Protocol):
    def score(self, evidence: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        """Phase 4+ — not implemented in Phase 3."""
        ...


class RiskEnginePort(Protocol):
    def assess(self, evidence: dict[str, Any], incidents: list[str], policy: dict[str, Any]) -> dict[str, Any]:
        """Phase 4+ — not implemented in Phase 3."""
        ...


class CapacityPlannerPort(Protocol):
    def plan(self, fleet_state: str, policy: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        """Phase 4+ — not implemented in Phase 3."""
        ...


class StubTrustEngine:
    def score(self, evidence: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        return {"implemented": False, "phase": 3, "score": None}


class StubRiskEngine:
    def assess(self, evidence: dict[str, Any], incidents: list[str], policy: dict[str, Any]) -> dict[str, Any]:
        return {"implemented": False, "phase": 3, "risk": None}


class StubCapacityPlanner:
    def plan(self, fleet_state: str, policy: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        return {"implemented": False, "phase": 3, "capacity": None}
