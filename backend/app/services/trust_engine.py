"""V67 Phase 4 — Trust Engine (deterministic, evidence-driven, no AI randomness)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

EVIDENCE_VERSION = "v67.4.trust.1"

# Fixed weights — must sum conceptually to 100 for explanation clarity.
_WEIGHTS = {
    "account_age_days": 8,
    "active_days": 8,
    "inbound_diversity": 10,
    "outbound_diversity": 8,
    "bidirectional_chats": 12,
    "response_ratio": 10,
    "delivery_success": 10,
    "webhook_freshness": 6,
    "queue_health": 6,
    "incident_free_days": 10,
    "device_stability": 4,
    "native_contacts": 4,
    "policy_compliance": 4,
}


@dataclass(frozen=True)
class TrustResult:
    score: float  # 0..100
    evidence_version: str
    components: dict[str, float]
    explanations: tuple[str, ...]
    missing: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["explanations"] = list(self.explanations)
        d["missing"] = list(self.missing)
        d["implemented"] = True
        d["phase"] = 4
        return d


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _num(evidence: dict, key: str, default: float | None = None) -> float | None:
    if key not in evidence or evidence[key] is None:
        return default
    try:
        return float(evidence[key])
    except (TypeError, ValueError):
        return default


class TrustEngine:
    """Pure deterministic Trust Score. No DB / Redis / Green API / randomness."""

    version = EVIDENCE_VERSION

    def score(self, evidence: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.evaluate(evidence or {}, policy or {}).as_dict()

    def evaluate(self, evidence: dict[str, Any], policy: dict[str, Any] | None = None) -> TrustResult:
        policy = policy or {}
        missing: list[str] = []
        components: dict[str, float] = {}
        explanations: list[str] = []

        def part(name: str, raw: float | None, frac_fn) -> float:
            w = float(_WEIGHTS[name])
            if raw is None:
                missing.append(name)
                components[name] = 0.0
                explanations.append(f"{name}=0 (missing)")
                return 0.0
            frac = _clamp(float(frac_fn(raw)), 0.0, 1.0)
            pts = round(frac * w, 2)
            components[name] = pts
            explanations.append(f"{name}={pts}/{w}")
            return pts

        age = _num(evidence, "account_age_days")
        part("account_age_days", age, lambda d: min(1.0, d / 30.0))

        active = _num(evidence, "active_days")
        part("active_days", active, lambda d: min(1.0, d / 10.0))

        in_div = _num(evidence, "inbound_diversity")
        if in_div is None:
            in_div = _num(evidence, "unique_inbound_chats")
        part("inbound_diversity", in_div, lambda n: min(1.0, n / 10.0))

        out_div = _num(evidence, "outbound_diversity")
        if out_div is None:
            out_div = _num(evidence, "unique_outbound_chats")
        part("outbound_diversity", out_div, lambda n: min(1.0, n / 8.0))

        bi = _num(evidence, "bidirectional_chats")
        part("bidirectional_chats", bi, lambda n: min(1.0, n / 5.0))

        resp = _num(evidence, "response_ratio")
        part("response_ratio", resp, lambda r: min(1.0, max(0.0, r)))

        deliv = _num(evidence, "delivery_success")
        if deliv is None:
            deliv = _num(evidence, "delivery_success_rate")
        part("delivery_success", deliv, lambda r: min(1.0, max(0.0, r)))

        wh = evidence.get("webhook_fresh")
        if wh is None and "webhook_freshness" in evidence:
            wh = evidence["webhook_freshness"]
        if isinstance(wh, (int, float)) and not isinstance(wh, bool):
            wh_f = float(wh)
        elif wh is True:
            wh_f = 1.0
        elif wh is False:
            wh_f = 0.0
        else:
            wh_f = None
        part("webhook_freshness", wh_f, lambda r: min(1.0, max(0.0, r)))

        qh = evidence.get("queue_health")
        if qh is True:
            qh_f = 1.0
        elif qh is False:
            qh_f = 0.0
        else:
            qh_f = _num(evidence, "queue_health") if not isinstance(qh, bool) else None
        part("queue_health", qh_f, lambda r: min(1.0, max(0.0, r)))

        ifree = _num(evidence, "incident_free_days")
        part("incident_free_days", ifree, lambda d: min(1.0, d / 14.0))

        dev = evidence.get("device_stability")
        if dev is True:
            dev_f = 1.0
        elif dev is False:
            dev_f = 0.0
        else:
            dev_f = _num(evidence, "device_stability")
        part("device_stability", dev_f, lambda r: min(1.0, max(0.0, r)))

        native = _num(evidence, "native_contacts")
        part("native_contacts", native, lambda n: min(1.0, n / 5.0) if n else 0.0)

        pc = evidence.get("policy_compliance")
        if pc is True:
            pc_f = 1.0
        elif pc is False:
            pc_f = 0.0
        elif policy:
            pc_f = 0.5
        else:
            pc_f = None
        part("policy_compliance", pc_f, lambda r: min(1.0, max(0.0, r)))

        total = round(sum(components.values()), 2)
        total = _clamp(total)
        # connected_at alone must not inflate — if only connected_at provided, score stays low
        if evidence.get("connected_at") and not any(
            evidence.get(k) for k in (
                "bidirectional_chats", "inbound_diversity", "unique_inbound_chats",
                "has_real_inbound", "active_days",
            )
        ):
            explanations.append("connected_at_alone_no_maturity_boost")
            total = min(total, 15.0)

        return TrustResult(
            score=total,
            evidence_version=self.version,
            components=components,
            explanations=tuple(explanations),
            missing=tuple(missing),
        )
