"""V67 Phase 7 — ShadowRuntimeService (observational only; never mutates runtime)."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.account import Account
from app.models.fleet_account import FleetAccount
from app.models.fleet_policy import FleetPolicy
from app.models.fleet_shadow import FleetShadowSnapshot
from app.services.shadow_comparison import ShadowComparisonEngine
from app.services.shadow_freshness import evaluate_freshness
from app.services.shadow_lock import ShadowAccountLock
from app.services.shadow_types import (
    SHADOW_VERSION, ShadowRunSource, ShadowThresholdStatus, idempotency_key,
)
from app.services import shadow_metrics
from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS
from app.services.fleet_state_adapter import FleetStateAdapter, SensorSnapshot
from app.services.journey_orchestrator import JourneyOrchestrator
from app.services.fleet_scoring import FleetScoringService
from app.services.capacity_planner import CapacityPlanner
from app.services.fleet_budget import FleetBudgetEngine
from app.services.campaign_eligibility import CampaignEligibilityEngine
from app.services.send_gate import can_send_now, is_account_send_eligible, get_cached_live_state


class ShadowRuntimeService:
    def __init__(self):
        self.comparison = ShadowComparisonEngine()
        self.scoring = FleetScoringService()
        self.capacity = CapacityPlanner()
        self.budget = FleetBudgetEngine()
        self.eligibility = CampaignEligibilityEngine()
        self.orchestrator = JourneyOrchestrator()

    def flags_enabled_for_periodic(self) -> bool:
        return bool(settings.v67_shadow_runtime_enabled) and bool(settings.v67_shadow_scheduler_enabled)

    async def run_account(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        *,
        source: str = ShadowRunSource.API_RUN_ONCE.value,
        persist: bool = False,
        dry_run: bool = True,
        scheduled_slot: datetime | None = None,
        inject: dict | None = None,
        require_runtime_flag: bool = False,
        use_lock: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.utcnow()
        inject = inject or {}
        shadow_metrics.incr("shadow_runs_total")

        if require_runtime_flag and not settings.v67_shadow_runtime_enabled:
            shadow_metrics.incr("shadow_skipped_disabled")
            return {
                "skipped": True, "reason": "v67_shadow_runtime_enabled_false",
                "simulation_only": True, "mutates_runtime": False, "executes": False,
            }

        lock = None
        if use_lock:
            lock = ShadowAccountLock(
                str(account_id), ttl=int(settings.v67_shadow_lock_ttl_seconds),
            )
            ok = await lock.acquire()
            if lock.fail_closed_reason:
                shadow_metrics.incr("shadow_lock_failures")
                return {
                    "error": "shadow_lock_redis_unavailable",
                    "simulation_only": True, "mutates_runtime": False, "executes": False,
                }
            if not ok:
                shadow_metrics.incr("shadow_lock_held")
                return {
                    "skipped": True, "reason": "shadow_lock_held",
                    "simulation_only": True, "mutates_runtime": False, "executes": False,
                }

        try:
            return await self._evaluate(
                db, account_id, source=source, persist=persist and not dry_run,
                dry_run=dry_run, scheduled_slot=scheduled_slot, inject=inject, now=now,
            )
        finally:
            if lock is not None:
                await lock.release()

    async def _evaluate(
        self,
        db: AsyncSession,
        account_id: uuid.UUID,
        *,
        source: str,
        persist: bool,
        dry_run: bool,
        scheduled_slot: datetime | None,
        inject: dict,
        now: datetime,
    ) -> dict[str, Any]:
        fleet = (await db.execute(
            select(FleetAccount).where(FleetAccount.account_id == account_id)
        )).scalar_one_or_none()
        acc = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
        if acc is None:
            return {"error": "account_not_found"}
        if fleet is None:
            return {"error": "fleet_account_missing"}
        if bool(fleet.cutover):
            shadow_metrics.incr("shadow_cutover_blocked")
            return {
                "error": "cutover_true_forbidden",
                "cutover": True,
                "simulation_only": True,
                "mutates_runtime": False,
                "executes": False,
            }

        policy_row = (await db.execute(
            select(FleetPolicy).where(FleetPolicy.is_default.is_(True)).limit(1)
        )).scalar_one_or_none()
        if policy_row:
            policy = {
                "name": policy_row.name, "version": policy_row.version,
                "settings_json": dict(policy_row.settings_json or {}),
            }
            policy_version = int(policy_row.version)
            policy_id = policy_row.id
            policy_source = f"db_default:{policy_row.name}"
        else:
            policy = {
                "name": "CONSERVATIVE", "version": 1,
                "settings_json": dict(CONSERVATIVE_POLICY_SETTINGS),
            }
            policy_version = 1
            policy_id = None
            policy_source = "explicit_conservative_default"

        # Ensure shadow_freshness present for explicit default only
        settings_json = dict(policy["settings_json"])
        if "shadow_freshness" not in settings_json and policy_source.startswith("explicit"):
            settings_json["shadow_freshness"] = dict(
                CONSERVATIVE_POLICY_SETTINGS.get("shadow_freshness") or {}
            )
            policy = {**policy, "settings_json": settings_json}

        score = await self.scoring.simulate(db, account_id, inject=inject, persist=False)
        if score.get("error"):
            return score
        evidence = dict(score.get("evidence") or {})
        if inject.get("breaker"):
            evidence["breaker"] = True
        if inject.get("incident"):
            evidence.setdefault("incidents", []).append(str(inject["incident"]))

        breaker = bool(inject.get("breaker") or evidence.get("breaker"))
        try:
            from app.services import fleet_breaker
            tripped, _ = await fleet_breaker.is_tripped(fail_closed=False)
            breaker = breaker or bool(tripped)
        except Exception:
            pass

        preview = await self.orchestrator.preview(db, account_id, inject=inject, now=now)
        adapter_state = None
        journey_rec = None
        if isinstance(preview, dict) and not preview.get("error"):
            adapter_state = preview.get("adapter_recommended")
            journey_rec = (preview.get("decision") or {}).get("recommended_next_state")

        status_val = getattr(getattr(acc, "status", None), "value", getattr(acc, "status", None))
        warmup_val = None
        # WarmupState may live on enrollment; keep optional
        for attr in ("warmup_state", "warmup_status"):
            if getattr(acc, attr, None) is not None:
                warmup_val = str(getattr(acc, attr))
                break

        live = inject.get("live_state")
        if live is None and not inject.get("runtime_unknown"):
            live = get_cached_live_state(getattr(acc, "instance_id", None), now)
        if inject.get("runtime_unknown"):
            live = None

        sensors = SensorSnapshot(
            account_status=str(status_val or ""),
            warmup_state=warmup_val,
            live_state=live,
            open_incidents=list(evidence.get("incidents") or []),
            fleet_breaker_tripped=breaker,
        )
        derived = FleetStateAdapter().derive(sensors, for_seed=False)
        canonical = fleet.fleet_state
        if inject.get("fleet_state"):
            canonical = str(inject["fleet_state"])
        if adapter_state is None:
            adapter_state = derived.recommended

        trust_score = float(score["trust"]["score"])
        risk_level = str(score["risk"]["level"])
        readiness = str(score["readiness"]["label"])
        if inject.get("trust_score") is not None:
            trust_score = float(inject["trust_score"])
        if inject.get("risk_level"):
            risk_level = str(inject["risk_level"])
        if inject.get("readiness_label"):
            readiness = str(inject["readiness_label"])

        cap = self.capacity.evaluate(
            fleet_state=canonical, policy=policy, evidence=evidence,
            trust_score=trust_score, risk_level=risk_level,
            used_today=int(getattr(acc, "sent_today", 0) or 0),
        )
        bud = self.budget.compute(
            daily_capacity=cap.daily_capacity,
            used_today=int(getattr(acc, "sent_today", 0) or 0),
            policy=policy,
        )

        journey_status = None
        if isinstance(preview, dict) and not preview.get("error"):
            # Phase 3 preview does not always expose journey row status; treat missing as None
            journey_status = inject.get("journey_status")
            if journey_status is None:
                journey_status = (preview.get("journey") or {}).get("status")
        elif inject.get("journey_status") is not None:
            journey_status = inject.get("journey_status")
        if inject.get("journey_status") is not None:
            journey_status = inject.get("journey_status")

        elig = self.eligibility.decide(
            fleet_state=canonical,
            journey_status=journey_status,
            trust_score=trust_score,
            risk_level=risk_level,
            readiness_label=readiness,
            daily_capacity=cap.daily_capacity,
            recommended_usage=bud.recommended_usage,
            remaining_budget=bud.remaining_budget,
            policy=policy,
            incidents=list(evidence.get("incidents") or []),
            breaker_tripped=breaker,
            evidence=evidence,
            policy_version=policy_version,
            policy_source=policy_source,
        )

        # Pure legacy eligibility — no async hydrate / no update_live_state
        legacy_allowed, legacy_reason = is_account_send_eligible(
            acc, live, breaker_tripped=breaker, unresolved_critical=False,
            require_live_state=False, now=now, live_state_known=(live is not None),
        )
        # Also record classic gate
        classic_ok, classic_reason = can_send_now(acc, live, now)

        sensor_timestamps = {
            "live_state": now if live is not None else None,
            "policy": now,
            "breaker": now,
            "incidents": now,
            "eligibility": now,
            "scoring": now,
            "capacity": now,
            "legacy_observation": now,
            "journey": now if journey_status else None,
            "webhook": evidence.get("webhook_checked_at"),
        }
        if inject.get("stale_sensor"):
            sensor_timestamps[str(inject["stale_sensor"])] = datetime(2000, 1, 1)
        if inject.get("policy_mismatch"):
            expected_pv = policy_version + 1
        else:
            expected_pv = policy_version

        freshness = evaluate_freshness(
            now=now, sensor_timestamps=sensor_timestamps, policy=policy,
        )

        comparison = self.comparison.compare(
            canonical_fleet_state=canonical,
            adapter_recommended_state=adapter_state or derived.recommended,
            journey_recommended_state=journey_rec,
            trust_score=trust_score,
            risk_level=risk_level,
            readiness_label=readiness,
            daily_capacity=cap.daily_capacity,
            recommended_usage=bud.recommended_usage,
            eligibility_decision=elig.decision,
            legacy_account_status=str(getattr(getattr(acc, "status", None), "value", getattr(acc, "status", "")) or ""),
            legacy_warmup_state=str(getattr(acc, "warmup_state", None) or ""),
            legacy_eligibility=legacy_reason,
            legacy_send_allowed=legacy_allowed and classic_ok,
            live_state=live,
            incidents=list(evidence.get("incidents") or []),
            breaker_tripped=breaker,
            sensor_freshness=freshness,
            policy_version=policy_version,
            expected_policy_version=expected_pv,
            evidence_complete=not bool(freshness.get("_fail_closed")),
            runtime_unknown=bool(inject.get("runtime_unknown")),
            journey_status=journey_status,
        )

        run_id = uuid.uuid4()
        slot_str = scheduled_slot.isoformat() if scheduled_slot else None
        idem = idempotency_key(
            str(account_id), SHADOW_VERSION, policy_version, slot_str, source,
        )
        out = {
            "simulation_only": True,
            "mutates_runtime": False,
            "executes": False,
            "dry_run": dry_run or not persist,
            "run_id": str(run_id),
            "account_id": str(account_id),
            "fleet_account_id": str(fleet.id),
            "cutover": False,
            "shadow_version": SHADOW_VERSION,
            "policy_version": policy_version,
            "policy_source": policy_source,
            "dangerous_threshold_status": ShadowThresholdStatus.UNRATIFIED.value,
            "comparison": comparison.as_dict(),
            "legacy": {
                "status": str(getattr(getattr(acc, "status", None), "value", getattr(acc, "status", None))),
                "warmup_state": str(getattr(acc, "warmup_state", None) or ""),
                "send_allowed": legacy_allowed and classic_ok,
                "send_reason": legacy_reason if not legacy_allowed else classic_reason,
                "live_state": live,
            },
            "v67": {
                "canonical_fleet_state": canonical,
                "adapter_recommended_state": adapter_state or derived.recommended,
                "journey_recommended_state": journey_rec,
                "trust_score": trust_score,
                "risk_level": risk_level,
                "readiness_label": readiness,
                "daily_capacity": cap.daily_capacity,
                "recommended_usage": bud.recommended_usage,
                "eligibility_decision": elig.decision,
                "journey_status": journey_status,
            },
            "sensor_freshness": freshness,
            "idempotency_key": idem,
            "source": source,
            "observed_at": now.isoformat(),
        }

        do_persist = (
            persist
            and not dry_run
            and bool(settings.v67_shadow_persistence_enabled)
        )
        if do_persist:
            existing = (await db.execute(
                select(FleetShadowSnapshot).where(FleetShadowSnapshot.idempotency_key == idem)
            )).scalar_one_or_none()
            if existing:
                shadow_metrics.incr("shadow_idempotent_skips")
                out["persisted"] = False
                out["duplicate"] = True
                out["snapshot_id"] = str(existing.id)
                return out
            snap = FleetShadowSnapshot(
                id=uuid.uuid4(),
                run_id=run_id,
                account_id=account_id,
                fleet_account_id=fleet.id,
                observed_at=now,
                scheduled_slot=scheduled_slot,
                source=source,
                shadow_version=SHADOW_VERSION,
                policy_id=policy_id,
                policy_version=policy_version,
                legacy_state=out["legacy"].get("status"),
                canonical_fleet_state=canonical,
                adapter_recommended_state=out["v67"]["adapter_recommended_state"],
                journey_recommended_state=journey_rec,
                trust_score=trust_score,
                risk_level=risk_level,
                readiness_label=readiness,
                daily_capacity=cap.daily_capacity,
                recommended_usage=bud.recommended_usage,
                eligibility_decision=elig.decision,
                legacy_eligibility=out["legacy"]["send_reason"],
                mismatch_class=comparison.mismatch_class,
                severity=comparison.severity,
                reason_codes=list(comparison.reason_codes),
                missing_evidence=list(comparison.missing_evidence),
                sensor_versions={"shadow": SHADOW_VERSION, "eligibility": elig.decision_version},
                sensor_freshness=freshness,
                legacy_snapshot=out["legacy"],
                v67_snapshot=out["v67"],
                comparison_snapshot=comparison.as_dict(),
                dangerous_threshold_status=ShadowThresholdStatus.UNRATIFIED.value,
                simulation_only=True,
                mutates_runtime=False,
                executes=False,
                idempotency_key=idem,
            )
            db.add(snap)
            try:
                await db.flush()
            except IntegrityError:
                shadow_metrics.incr("shadow_idempotent_skips")
                out["persisted"] = False
                out["duplicate"] = True
                return out
            out["snapshot_id"] = str(snap.id)
            out["persisted"] = True
            shadow_metrics.incr("shadow_persisted")
        else:
            out["persisted"] = False

        shadow_metrics.incr(f"shadow_mismatch_{comparison.mismatch_class}")
        shadow_metrics.incr(f"shadow_severity_{comparison.severity}")
        shadow_metrics.incr("shadow_runs_success")
        return out

    async def run_batch_periodic(self, db: AsyncSession, *, limit: int | None = None) -> dict[str, Any]:
        """Periodic entry — no-ops unless both flags true."""
        if not self.flags_enabled_for_periodic():
            shadow_metrics.incr("shadow_skipped_disabled")
            return {
                "skipped": True,
                "reason": "shadow_flags_disabled",
                "processed": 0,
                "simulation_only": True,
                "mutates_runtime": False,
                "executes": False,
            }
        limit = int(limit or settings.v67_shadow_batch_size)
        fleets = list(
            (await db.execute(
                select(FleetAccount)
                .where(FleetAccount.cutover.is_(False))
                .order_by(FleetAccount.account_id)
                .limit(limit)
            )).scalars().all()
        )
        results = []
        # No catch-up: use current slot floor to minute
        slot = datetime.utcnow().replace(second=0, microsecond=0)
        for f in fleets:
            try:
                row = await self.run_account(
                    db, f.account_id,
                    source=ShadowRunSource.CELERY_PERIODIC.value,
                    persist=True, dry_run=False,
                    scheduled_slot=slot,
                    require_runtime_flag=True,
                    use_lock=True,
                )
                results.append({"account_id": str(f.account_id), "ok": "error" not in row})
            except Exception as e:
                shadow_metrics.incr("shadow_runs_failed")
                results.append({"account_id": str(f.account_id), "ok": False, "error": str(e)})
        return {
            "processed": len(results),
            "results": results,
            "simulation_only": True,
            "mutates_runtime": False,
            "executes": False,
        }
