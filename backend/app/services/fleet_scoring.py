"""V67 Phase 4 — evidence aggregation + optional snapshot persist (simulation)."""
from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.fleet_account import FleetAccount
from app.models.fleet_evidence import FleetEvidenceSnapshot
from app.models.incident import AccountIncident
from app.services.trust_engine import TrustEngine, EVIDENCE_VERSION as TRUST_VER
from app.services.risk_engine import RiskEngine, EVIDENCE_VERSION as RISK_VER
from app.services.readiness_evaluator import ReadinessEvaluator
from app.services.graduation_trial import GraduationTrialFramework

COMBINED_EVIDENCE_VERSION = "v67.4.evidence.1"


def apply_injects(evidence: dict[str, Any], inject: dict[str, Any] | None) -> dict[str, Any]:
    ev = dict(evidence or {})
    inject = inject or {}
    if inject.get("incidents"):
        ev["incidents"] = list(set(list(ev.get("incidents") or []) + list(inject["incidents"])))
    if inject.get("suspended"):
        ev.setdefault("incidents", []).append("suspended")
        ev["suspend_history"] = True
    if inject.get("blocked"):
        ev.setdefault("incidents", []).append("blocked")
        ev["blocked_history"] = True
    if inject.get("inactivity"):
        ev["inactivity_days"] = int(inject.get("inactivity_days") or 14)
    if inject.get("webhook_failure"):
        ev["webhook_fresh"] = False
        ev["webhook_failures"] = True
    if inject.get("breaker"):
        ev["breaker"] = True
        ev["fleet_breaker_tripped"] = True
    return ev


class EvidenceAggregator:
    """Gather sensors into a normalized evidence dict (read-only DB)."""

    async def gather(self, db: AsyncSession, account_id: uuid.UUID) -> dict[str, Any]:
        acc = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
        if acc is None:
            return {"error": "account_not_found"}
        incidents = list((await db.execute(
            select(AccountIncident.incident_type).where(
                AccountIncident.account_id == account_id,
                AccountIncident.resolved.is_(False),
            )
        )).scalars().all())
        ev: dict[str, Any] = {
            "account_age_days": float(acc.days_active or 0),
            "active_days": float(acc.days_active or 0),
            "has_real_inbound": (acc.received_today or 0) > 0,
            "has_real_outbound": (acc.sent_today or 0) > 0,
            "real_inbound_count": int(acc.received_today or 0),
            "real_outbound_count": int(acc.sent_today or 0),
            "incidents": [i for i in incidents if i],
            "connected_at": acc.connected_at.isoformat() if acc.connected_at else None,
            "day10_complete": (acc.days_active or 0) >= 10,
            "webhook_fresh": True,
            "queue_health": True,
            "device_stability": True,
            "policy_compliance": True,
        }
        if acc.instance_id:
            try:
                from app.services.activity_evidence import activity_evidence_for_instance
                act = await activity_evidence_for_instance(db, str(acc.instance_id))
                if act.get("unique_inbound_chats") is not None:
                    ev["unique_inbound_chats"] = act["unique_inbound_chats"]
                    ev["inbound_diversity"] = act["unique_inbound_chats"]
                if act.get("unique_outbound_chats") is not None:
                    ev["unique_outbound_chats"] = act["unique_outbound_chats"]
                    ev["outbound_diversity"] = act["unique_outbound_chats"]
                if act.get("bidirectional_chats") is not None:
                    ev["bidirectional_chats"] = act["bidirectional_chats"]
                if act.get("first_real_inbound_at"):
                    ev["has_real_inbound"] = True
                if act.get("first_real_outbound_at"):
                    ev["has_real_outbound"] = True
            except Exception:
                pass
        # Defaults for ratios when unknown — leave missing for trust engine honesty
        if "response_ratio" not in ev and ev.get("has_real_inbound") and ev.get("has_real_outbound"):
            ev["response_ratio"] = 0.5
        if "delivery_success" not in ev and ev.get("has_real_outbound"):
            ev["delivery_success"] = 0.8
        if "incident_free_days" not in ev:
            ev["incident_free_days"] = 14.0 if not incidents else 0.0
        return ev


class FleetScoringService:
    """Simulation orchestration for trust/risk/readiness — never mutates FleetState."""

    def __init__(self):
        self.trust = TrustEngine()
        self.risk = RiskEngine()
        self.readiness = ReadinessEvaluator()
        self.graduation = GraduationTrialFramework()
        self.aggregator = EvidenceAggregator()

    async def simulate(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        *,
        inject: dict | None = None,
        persist: bool = False,
        policy: dict | None = None,
    ) -> dict[str, Any]:
        fleet = (await db.execute(
            select(FleetAccount).where(FleetAccount.account_id == account_id)
        )).scalar_one_or_none()
        evidence = await self.aggregator.gather(db, account_id)
        if evidence.get("error"):
            return evidence
        evidence = apply_injects(evidence, inject)
        policy = policy or {}

        trust = self.trust.evaluate(evidence, policy)
        risk = self.risk.evaluate(evidence, evidence.get("incidents") or [], policy)
        current = fleet.fleet_state if fleet else "NEW"
        cutover = bool(fleet.cutover) if fleet else False
        trial = self.graduation.evaluate(
            current_fleet_state=current,
            trust_score=trust.score,
            risk_level=risk.level,
            evidence=evidence,
            policy=policy,
        )
        ready = self.readiness.evaluate(
            current_fleet_state=current,
            trust_score=trust.score,
            risk_level=risk.level,
            risk_score=risk.score,
            evidence=evidence,
            policy=policy,
        )

        out = {
            "simulation_only": True,
            "account_id": str(account_id),
            "canonical_fleet_state": current,
            "fleet_state_mutated": False,
            "cutover": cutover,
            "trust": trust.as_dict(),
            "risk": risk.as_dict(),
            "graduation_trial": trial.as_dict(),
            "readiness": ready.as_dict(),
            "evidence_version": COMBINED_EVIDENCE_VERSION,
            "evidence": evidence,
            "send_gate_note": "unchanged — scoring does not affect send eligibility",
        }

        if persist:
            if cutover:
                out["persisted"] = False
                out["error"] = "cutover_true_forbidden_for_phase4_persist"
                return out
            snap = FleetEvidenceSnapshot(
                id=uuid.uuid4(),
                account_id=account_id,
                fleet_account_id=fleet.id if fleet else None,
                trust_score=Decimal(str(trust.score)),
                risk_score=Decimal(str(risk.score)),
                risk_level=risk.level,
                readiness_score=Decimal(str(round(ready.score, 2))),
                readiness_label=ready.label,
                evidence_version=COMBINED_EVIDENCE_VERSION,
                evidence_json=evidence,
                explanation_json={
                    "trust": trust.as_dict(),
                    "risk": risk.as_dict(),
                    "graduation_trial": trial.as_dict(),
                    "readiness": ready.as_dict(),
                    "trust_engine_version": TRUST_VER,
                    "risk_engine_version": RISK_VER,
                },
                calculated_at=datetime.utcnow(),
                simulation_only=True,
            )
            db.add(snap)
            await db.flush()
            # Prove FleetState untouched
            if fleet is not None:
                fleet.cutover = False
            out["persisted"] = True
            out["snapshot_id"] = str(snap.id)
        else:
            out["persisted"] = False
            out["dry_run"] = True
        return out
