"""V67 Phase 3/4/5 — Trust / Risk / Capacity ports.

Phase 5: CapacityPlanner is a real deterministic implementation.
"""
from __future__ import annotations
from typing import Protocol, Any

from app.services.trust_engine import TrustEngine
from app.services.risk_engine import RiskEngine
from app.services.capacity_planner import CapacityPlanner


class TrustEnginePort(Protocol):
    def score(self, evidence: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        ...


class RiskEnginePort(Protocol):
    def assess(self, evidence: dict[str, Any], incidents: list[str], policy: dict[str, Any]) -> dict[str, Any]:
        ...


class CapacityPlannerPort(Protocol):
    def plan(self, fleet_state: str, policy: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        ...


class StubTrustEngine(TrustEngine):
    pass


class StubRiskEngine(RiskEngine):
    pass


class StubCapacityPlanner(CapacityPlanner):
    """Phase 5: real CapacityPlanner (name kept for orchestrator imports)."""
