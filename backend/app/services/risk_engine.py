"""V67 Phase 4 — Risk Engine (deterministic levels; never mutates runtime)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

EVIDENCE_VERSION = "v67.4.risk.1"

RiskLevel = str  # NORMAL | LOW | MEDIUM | HIGH | CRITICAL


@dataclass(frozen=True)
class RiskResult:
    score: float  # 0..100 higher = worse
    level: RiskLevel
    evidence_version: str
    factors: dict[str, float]
    explanations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["explanations"] = list(self.explanations)
        d["risk"] = self.level
        d["implemented"] = True
        d["phase"] = 4
        return d


def _level_for(score: float) -> RiskLevel:
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    if score >= 20:
        return "LOW"
    return "NORMAL"


class RiskEngine:
    """Pure deterministic Risk Score. No runtime mutation."""

    version = EVIDENCE_VERSION

    def assess(
        self,
        evidence: dict[str, Any],
        incidents: list[str] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.evaluate(evidence or {}, incidents or [], policy or {}).as_dict()

    def evaluate(
        self,
        evidence: dict[str, Any],
        incidents: list[str] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> RiskResult:
        incidents = [str(i) for i in (incidents or []) if i]
        # Also merge from evidence
        for i in evidence.get("incidents") or []:
            if i and str(i) not in incidents:
                incidents.append(str(i))

        factors: dict[str, float] = {}
        explanations: list[str] = []

        def add(name: str, pts: float, why: str) -> None:
            if pts <= 0:
                return
            factors[name] = round(pts, 2)
            explanations.append(why)

        # Major incidents
        if "blocked" in incidents or evidence.get("blocked_history"):
            add("blocked", 40, "blocked_history_or_open")
        if "suspended" in incidents or evidence.get("suspend_history"):
            add("suspended", 45, "suspend_history_or_open")
        if "forced_logout" in incidents or evidence.get("logout_history"):
            add("forced_logout", 30, "logout_history_or_open")
        if "device_restriction" in incidents:
            add("device_restriction", 30, "device_restriction_open")
        if "yellowCard" in incidents or "yellowcard" in [x.lower() for x in incidents]:
            add("yellowcard", 20, "yellowcard_open")
        if "auth_churn" in incidents:
            add("auth_churn", 18, "auth_churn_open")

        if evidence.get("breaker") or evidence.get("fleet_breaker_tripped"):
            add("breaker", 25, "fleet_breaker_tripped")
        if evidence.get("webhook_failures") or evidence.get("webhook_fresh") is False:
            add("webhook_failures", 15, "webhook_failures_or_stale")
        if (evidence.get("queue_backlog") or 0) > 50 or evidence.get("queue_health") is False:
            add("queue_backlog", 12, "queue_backlog_or_unhealthy")
        if (evidence.get("duplicate_sends") or 0) > 0:
            add("duplicate_sends", min(20.0, 5.0 * float(evidence.get("duplicate_sends") or 0)), "duplicate_sends")
        if (evidence.get("inactivity_days") or 0) >= 7:
            add("inactivity", min(25.0, float(evidence["inactivity_days"])), "inactivity_days")
        if evidence.get("sudden_traffic_spike"):
            add("traffic_spike", 15, "sudden_traffic_spike")
        if (evidence.get("repeated_templates") or 0) >= 5:
            add("repeated_templates", 10, "repeated_templates")
        if evidence.get("device_reuse"):
            add("device_reuse", 12, "device_reuse_flag")

        # Count historical signals
        for key, pts in (
            ("suspend_count_30d", 8),
            ("block_count_30d", 10),
            ("logout_count_30d", 8),
        ):
            n = float(evidence.get(key) or 0)
            if n > 0:
                add(key, min(30.0, pts * n), f"{key}={n}")

        score = round(min(100.0, sum(factors.values())), 2)
        level = _level_for(score)
        return RiskResult(
            score=score,
            level=level,
            evidence_version=self.version,
            factors=factors,
            explanations=tuple(explanations),
        )
