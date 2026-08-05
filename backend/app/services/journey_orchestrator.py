"""V67 Phase 3 — Simulation / Shadow journey orchestrator (no live send cutover)."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.fleet_account import FleetAccount
from app.models.fleet_policy import FleetPolicy
from app.models.account_journey import AccountJourney
from app.models.journey_action import JourneyAction
from app.models.incident import AccountIncident
from app.models.instance_state import InstanceLiveState
from app.models.warmup_mesh import WarmupEnrollment
from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS
from app.services.fleet_state_adapter import FleetStateAdapter, SensorSnapshot
from app.services.journey_transition import evaluate_transition, make_idempotency_key
from app.services.journey_shadow import compare_shadow
from app.services.journey_types import JourneyStatus, JourneyActionStatus, JourneyType, FORBIDDEN_LIVE_ACTION_TYPES
from app.services.fleet_engine_ports import StubTrustEngine, StubRiskEngine, StubCapacityPlanner


class JourneyOrchestrator:
    """SIMULATION / SHADOW only. Never sets cutover=True. Never calls Green API."""

    MODE_SIMULATION = "SIMULATION"
    MODE_SHADOW = "SHADOW"

    def __init__(self):
        self.adapter = FleetStateAdapter()
        self.trust = StubTrustEngine()
        self.risk = StubRiskEngine()
        self.capacity = StubCapacityPlanner()

    async def _load_sensors(self, db: AsyncSession, account: Account) -> dict[str, Any]:
        incidents = list((await db.execute(
            select(AccountIncident.incident_type).where(
                AccountIncident.account_id == account.id,
                AccountIncident.resolved.is_(False),
            )
        )).scalars().all())
        live = None
        if account.instance_id:
            row = (await db.execute(
                select(InstanceLiveState).where(InstanceLiveState.instance_id == str(account.instance_id))
            )).scalar_one_or_none()
            live = row.state if row else None
        enr = None
        if account.instance_id:
            enr = (await db.execute(
                select(WarmupEnrollment).where(
                    WarmupEnrollment.instance_id == str(account.instance_id)).limit(1)
            )).scalar_one_or_none()
        breaker = False
        try:
            from app.services import fleet_breaker
            tripped, _ = await fleet_breaker.is_tripped(fail_closed=False)
            breaker = bool(tripped)
        except Exception:
            breaker = False
        evidence: dict[str, Any] = {
            "connected_at": account.connected_at.isoformat() if account.connected_at else None,
            "authorized_at": account.authorized_at.isoformat() if getattr(account, "authorized_at", None) else None,
            "has_real_inbound": (account.received_today or 0) > 0,
            "has_real_outbound": (account.sent_today or 0) > 0,
            "real_inbound_count": int(account.received_today or 0),
            "real_outbound_count": int(account.sent_today or 0),
            "total_flow": int(account.received_today or 0) + int(account.sent_today or 0),
            "ramp_day_index": min(int(account.days_active or 0), 6),
            "day10_complete": (account.days_active or 0) >= 10,
        }
        if account.instance_id:
            try:
                from app.services.activity_evidence import activity_evidence_for_instance
                ev = await activity_evidence_for_instance(db, str(account.instance_id))
                if ev.get("first_real_inbound_at"):
                    evidence["first_real_inbound_at"] = ev["first_real_inbound_at"]
                    evidence["has_real_inbound"] = True
                if ev.get("first_real_outbound_at"):
                    evidence["first_real_outbound_at"] = ev["first_real_outbound_at"]
                    evidence["has_real_outbound"] = True
                if ev.get("bidirectional_chats"):
                    evidence["bidirectional_chats"] = ev["bidirectional_chats"]
                    evidence["has_bidirectional"] = True
            except Exception:
                pass
        return {
            "incidents": [i for i in incidents if i],
            "live": live,
            "warmup": getattr(enr, "state", None) if enr else None,
            "breaker": breaker,
            "evidence": evidence,
            "status": getattr(account.status, "value", account.status),
        }

    def _policy_snapshot(self, policy: FleetPolicy | None) -> dict:
        if policy is None:
            return {
                "name": "CONSERVATIVE",
                "version": 1,
                "settings_json": dict(CONSERVATIVE_POLICY_SETTINGS),
            }
        return {
            "id": str(policy.id),
            "name": policy.name,
            "version": policy.version,
            "settings_json": dict(policy.settings_json or {}),
        }

    async def preview(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        *,
        journey_type: str = JourneyType.NEW_ACCOUNT.value,
        inject: dict | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.utcnow()
        inject = inject or {}
        account = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
        if account is None:
            return {"error": "account_not_found"}
        fleet = (await db.execute(
            select(FleetAccount).where(FleetAccount.account_id == account_id)
        )).scalar_one_or_none()
        policy = None
        if fleet and fleet.policy_id:
            policy = (await db.execute(
                select(FleetPolicy).where(FleetPolicy.id == fleet.policy_id)
            )).scalar_one_or_none()
        if policy is None:
            policy = (await db.execute(
                select(FleetPolicy).where(FleetPolicy.is_default.is_(True)).limit(1)
            )).scalar_one_or_none()

        sensors = await self._load_sensors(db, account)
        if inject.get("suspended"):
            sensors["incidents"] = list(set(sensors["incidents"] + ["suspended"]))
            sensors["live"] = "suspended"
        if inject.get("blocked"):
            sensors["incidents"] = list(set(sensors["incidents"] + ["blocked"]))
            sensors["live"] = "blocked"
        if inject.get("forced_logout"):
            sensors["incidents"] = list(set(sensors["incidents"] + ["forced_logout"]))
        if inject.get("breaker"):
            sensors["breaker"] = True
        if inject.get("webhook_stale"):
            sensors["evidence"]["webhook_fresh"] = False

        snap = self._policy_snapshot(policy)
        current = fleet.fleet_state if fleet else "NEW"
        evidence = dict(sensors["evidence"])
        evidence["journey_started_at"] = now - timedelta(hours=float(inject.get("elapsed_hours", 0) or 0))
        if inject.get("days") is not None:
            evidence["ramp_day_index"] = int(inject["days"])
            evidence["day10_complete"] = int(inject["days"]) >= 10

        decision = evaluate_transition(
            current_state=current,
            journey_type=journey_type,
            policy_snapshot=snap,
            evidence=evidence,
            live_sensor_state=sensors["live"],
            incidents=sensors["incidents"],
            breaker_state=sensors["breaker"],
            now=now,
        )
        adapter = self.adapter.derive(SensorSnapshot(
            account_status=sensors["status"],
            warmup_state=sensors["warmup"],
            live_state=sensors["live"],
            open_incidents=sensors["incidents"],
            fleet_breaker_tripped=sensors["breaker"],
            has_real_inbound=bool(evidence.get("has_real_inbound")),
            has_real_outbound=bool(evidence.get("has_real_outbound")),
        ), for_seed=True)
        shadow = compare_shadow(
            canonical=current,
            adapter_recommended=adapter.recommended,
            journey_recommended=decision.recommended_next_state,
            account_status=sensors["status"],
            warmup_state=sensors["warmup"],
            live_state=sensors["live"],
            incidents=sensors["incidents"],
            evidence_complete=inject.get("webhook_stale") is not True,
        )
        # Interface stubs — prove not scoring
        trust = self.trust.score(evidence, snap.get("settings_json") or {})
        risk = self.risk.assess(evidence, sensors["incidents"], snap.get("settings_json") or {})
        capacity = self.capacity.plan(current, snap.get("settings_json") or {}, evidence)

        return {
            "mode": self.MODE_SHADOW,
            "account_id": str(account_id),
            "fleet_account_id": str(fleet.id) if fleet else None,
            "cutover": bool(fleet.cutover) if fleet else False,
            "canonical_fleet_state": current,
            "decision": {
                "current_state": decision.current_state,
                "recommended_next_state": decision.recommended_next_state,
                "allowed": decision.allowed,
                "reason_codes": list(decision.reason_codes),
                "missing_evidence": list(decision.missing_evidence),
                "required_wait_seconds": decision.required_wait_seconds,
                "planned_action_types": list(decision.planned_action_types),
                "risk_flags": list(decision.risk_flags),
                "policy_version": decision.policy_version,
            },
            "adapter_recommended": adapter.recommended,
            "shadow": {"label": shadow.label, "reasons": list(shadow.reasons), "details": shadow.details},
            "engine_ports": {"trust": trust, "risk": risk, "capacity": capacity},
            "send_gate_note": "send_gate remains runtime authority; FleetState not cut over",
            "simulation_only": True,
        }

    async def simulate_and_maybe_persist(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        *,
        journey_type: str = JourneyType.NEW_ACCOUNT.value,
        persist_simulation: bool = False,
        inject: dict | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        preview = await self.preview(
            db, account_id, journey_type=journey_type, inject=inject, now=now,
        )
        if preview.get("error"):
            return preview
        if not persist_simulation:
            return {**preview, "persisted": False, "dry_run": True}

        account = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one()
        fleet = (await db.execute(
            select(FleetAccount).where(FleetAccount.account_id == account_id)
        )).scalar_one_or_none()
        if fleet is None:
            return {**preview, "error": "fleet_account_required_for_persist", "persisted": False}
        # Never enable cutover in Phase 3
        if bool(fleet.cutover):
            return {**preview, "error": "cutover_true_forbidden_in_phase3", "persisted": False}

        policy = None
        if fleet.policy_id:
            policy = (await db.execute(
                select(FleetPolicy).where(FleetPolicy.id == fleet.policy_id)
            )).scalar_one_or_none()
        snap = self._policy_snapshot(policy)
        now = now or datetime.utcnow()
        decision = preview["decision"]

        existing = (await db.execute(
            select(AccountJourney).where(
                AccountJourney.fleet_account_id == fleet.id,
                AccountJourney.status.in_([
                    JourneyStatus.ACTIVE.value, JourneyStatus.PAUSED.value, JourneyStatus.SIMULATING.value,
                ]),
            )
        )).scalar_one_or_none()
        if existing:
            journey = existing
            journey.evidence_snapshot = preview.get("shadow", {})
            journey.version = int(journey.version or 1) + 1
            journey.updated_at = now
        else:
            journey = AccountJourney(
                id=uuid.uuid4(),
                account_id=account.id,
                fleet_account_id=fleet.id,
                journey_type=journey_type,
                profile_policy_id=fleet.policy_id,
                status=JourneyStatus.SIMULATING.value,
                current_state=preview["canonical_fleet_state"] or "NEW",
                started_at=now,
                state_changed_at=now,
                policy_snapshot=snap,
                evidence_snapshot={"preview": preview["decision"]},
                simulation_only=True,
                shadow_mode=True,
                version=1,
            )
            db.add(journey)
            await db.flush()

        planned = []
        slot = now.strftime("%Y%m%d%H")
        for atype in decision["planned_action_types"]:
            if atype in FORBIDDEN_LIVE_ACTION_TYPES:
                continue
            key = make_idempotency_key(str(account.id), str(journey.id), atype, slot)
            found = (await db.execute(
                select(JourneyAction).where(JourneyAction.idempotency_key == key)
            )).scalar_one_or_none()
            if found:
                planned.append({"action_type": atype, "idempotency_key": key, "duplicate": True})
                continue
            act = JourneyAction(
                id=uuid.uuid4(),
                journey_id=journey.id,
                account_id=account.id,
                action_type=atype,
                status=JourneyActionStatus.PLANNED.value,
                scheduled_at=now,
                idempotency_key=key,
                source_type="simulation",
                payload_json={"reason_codes": decision["reason_codes"]},
                simulation_only=True,
            )
            db.add(act)
            planned.append({"action_type": atype, "idempotency_key": key, "duplicate": False})
        await db.flush()
        # Do NOT mutate fleet.fleet_state for prod-like; cutover stays false
        fleet.cutover = False
        return {
            **preview,
            "persisted": True,
            "dry_run": False,
            "journey_id": str(journey.id),
            "planned_actions": planned,
            "cutover": fleet.cutover,
        }
