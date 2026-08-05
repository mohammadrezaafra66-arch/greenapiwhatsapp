"""V67 Phase 3 — pure deterministic journey transition engine (no IO)."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.services.fleet_state import FleetState, SEED_FORBIDDEN_AUTO_STATES
from app.services.fleet_policy_defaults import validate_policy_settings
from app.services.journey_types import (
    JourneyType, JourneyActionType, NEW_ACCOUNT_LADDER, PHASE3_TERMINAL_PROGRESS,
)


@dataclass(frozen=True)
class TransitionDecision:
    current_state: str
    recommended_next_state: str
    allowed: bool
    reason_codes: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    required_wait_seconds: int | None
    planned_action_types: tuple[str, ...]
    risk_flags: tuple[str, ...]
    policy_version: int | None
    journey_type: str


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return None


def _hours_since(ts: datetime | None, now: datetime) -> float | None:
    if ts is None:
        return None
    return max(0.0, (now - ts).total_seconds() / 3600.0)


def _policy_ok(policy_snapshot: dict | None) -> tuple[bool, str, int | None]:
    if not policy_snapshot or not isinstance(policy_snapshot, dict):
        return False, "missing_policy", None
    settings = policy_snapshot.get("settings_json") or policy_snapshot.get("settings") or policy_snapshot
    if not isinstance(settings, dict):
        return False, "invalid_policy_shape", None
    ok, msg = validate_policy_settings(settings)
    if not ok:
        return False, f"invalid_policy:{msg}", None
    if settings.get("flow_metric") != "incoming_plus_outgoing":
        return False, "flow_metric_must_be_incoming_plus_outgoing", None
    curve = settings.get("ramp_curve") or []
    if curve != sorted(curve):
        return False, "ramp_curve_not_ordered", None
    ver = policy_snapshot.get("version")
    return True, "ok", int(ver) if ver is not None else None


def evaluate_transition(
    current_state: str,
    journey_type: str,
    policy_snapshot: dict | None,
    evidence: dict | None,
    live_sensor_state: str | None,
    incidents: list[str] | None,
    breaker_state: bool | str | None,
    now: datetime,
) -> TransitionDecision:
    """Deterministic, side-effect-free transition recommendation."""
    evidence = evidence or {}
    incidents = [str(i) for i in (incidents or []) if i]
    live = (live_sensor_state or "").strip().lower() or None
    breaker_tripped = breaker_state is True or breaker_state == "tripped"
    cur = (current_state or FleetState.NEW.value).strip()

    ok_pol, pol_reason, pol_ver = _policy_ok(policy_snapshot)
    settings = {}
    if ok_pol and policy_snapshot:
        settings = policy_snapshot.get("settings_json") or policy_snapshot.get("settings") or policy_snapshot

    def decide(
        nxt: str,
        allowed: bool,
        reasons: list[str],
        missing: list[str] | None = None,
        wait: int | None = None,
        actions: list[str] | None = None,
        risks: list[str] | None = None,
    ) -> TransitionDecision:
        # Phase 3 hard caps
        if nxt in SEED_FORBIDDEN_AUTO_STATES or nxt in (
            FleetState.CAMPAIGN_READY.value, FleetState.MATURE.value,
            FleetState.GRADUATION_TRIAL.value, FleetState.MAINTENANCE.value,
        ):
            nxt = FleetState.WARMUP_READY.value
            reasons = list(reasons) + ["phase3_cap_warmup_ready"]
            allowed = allowed and (cur == FleetState.WARMUP_READY.value or nxt == FleetState.WARMUP_READY.value)
        return TransitionDecision(
            current_state=cur,
            recommended_next_state=nxt,
            allowed=allowed,
            reason_codes=tuple(reasons),
            missing_evidence=tuple(missing or ()),
            required_wait_seconds=wait,
            planned_action_types=tuple(actions or (JourneyActionType.REEVALUATE.value,)),
            risk_flags=tuple(risks or ()),
            policy_version=pol_ver,
            journey_type=journey_type,
        )

    # --- Precedence 1–8 (danger / pause) ---
    if cur == FleetState.RETIRED.value or live == "deleted":
        return decide(FleetState.RETIRED.value, False, ["terminal_retired"], actions=[JourneyActionType.REQUIRE_OWNER_REVIEW.value])
    if cur == FleetState.FAILED.value:
        return decide(FleetState.FAILED.value, False, ["terminal_failed"], actions=[JourneyActionType.REQUIRE_OWNER_REVIEW.value])

    if live == "blocked" or "blocked" in incidents or cur == FleetState.BLOCKED.value:
        return decide(FleetState.BLOCKED.value, False, ["blocked_override"],
                      risks=["major_incident"], actions=[JourneyActionType.REQUIRE_OWNER_REVIEW.value, JourneyActionType.PAUSE.value])
    if "forced_logout" in incidents or "device_restriction" in incidents or cur == FleetState.FORCED_LOGOUT.value:
        return decide(FleetState.FORCED_LOGOUT.value, False, ["forced_logout_or_device"],
                      risks=["major_incident", "rewarm_required"],
                      actions=[JourneyActionType.REQUIRE_OWNER_REVIEW.value])
    if live == "suspended" or "suspended" in incidents or cur == FleetState.SUSPENDED.value:
        return decide(FleetState.SUSPENDED.value, False, ["suspended_override"],
                      risks=["major_incident", "rewarm_required"],
                      actions=[JourneyActionType.PAUSE.value, JourneyActionType.REQUIRE_OWNER_REVIEW.value])
    if breaker_tripped:
        return decide(FleetState.PAUSED.value, False, ["fleet_breaker"],
                      risks=["breaker"], actions=[JourneyActionType.PAUSE.value])
    if any(i in ("yellowCard", "auth_churn") for i in incidents):
        return decide(FleetState.AT_RISK.value, False, ["critical_incident_open"],
                      risks=["yellowcard_or_churn"], actions=[JourneyActionType.CHECK_EVIDENCE.value])
    if cur == FleetState.PAUSED.value or evidence.get("explicit_paused"):
        return decide(FleetState.PAUSED.value, False, ["explicit_paused"],
                      actions=[JourneyActionType.REQUIRE_OWNER_REVIEW.value])

    if not ok_pol:
        return decide(cur, False, [pol_reason, "fail_closed_policy"],
                      missing=["valid_policy"], actions=[JourneyActionType.REQUIRE_OWNER_REVIEW.value])

    # Rewarm route
    if cur == FleetState.REWARM_REQUIRED.value or journey_type == JourneyType.REWARM.value:
        if live == "authorized":
            return decide(FleetState.AUTHORIZED_QUIET.value, True, ["rewarm_authorized_quiet"],
                          actions=[JourneyActionType.VERIFY_STATE.value, JourneyActionType.CHECK_EVIDENCE.value])
        return decide(FleetState.PRECHECK.value, True, ["rewarm_to_precheck"],
                      actions=[JourneyActionType.VERIFY_STATE.value, JourneyActionType.WAIT.value])

    # Maintenance evaluation-only
    if journey_type == JourneyType.MAINTENANCE.value:
        return decide(cur if cur else FleetState.WARMUP_READY.value, False, ["maintenance_eval_only"],
                      actions=[JourneyActionType.CHECK_EVIDENCE.value, JourneyActionType.REEVALUATE.value])

    # Normal progression — stop at WARMUP_READY
    if cur == PHASE3_TERMINAL_PROGRESS:
        return decide(FleetState.WARMUP_READY.value, False, ["phase3_stop_at_warmup_ready"],
                      actions=[JourneyActionType.CHECK_EVIDENCE.value])

    ladder = list(NEW_ACCOUNT_LADDER)
    if journey_type in (JourneyType.EXISTING_WARM.value, JourneyType.INACTIVE_AUTHORIZED.value):
        # Enter ladder at AUTHORIZED_QUIET if already authorized
        if live == "authorized" and cur in (FleetState.NEW.value, FleetState.PRECHECK.value):
            cur_eff = FleetState.AUTHORIZED_QUIET.value
        else:
            cur_eff = cur
    else:
        cur_eff = cur

    if cur_eff not in ladder:
        # Unknown mid-state: conservative reevaluate
        return decide(cur, False, ["state_not_on_phase3_ladder"],
                      actions=[JourneyActionType.REEVALUATE.value])

    idx = ladder.index(cur_eff)
    if idx >= len(ladder) - 1:
        return decide(FleetState.WARMUP_READY.value, False, ["already_terminal_progress"],
                      actions=[JourneyActionType.CHECK_EVIDENCE.value])

    nxt = ladder[idx + 1]
    missing: list[str] = []
    wait: int | None = None
    actions = [JourneyActionType.CHECK_EVIDENCE.value, JourneyActionType.REEVALUATE.value]

    qr_wait_h = float(settings.get("qr_wait_hours", 24))
    quiet_min_h = float(settings.get("authorized_quiet_hours", 1))

    if cur_eff == FleetState.NEW.value:
        return decide(FleetState.PRECHECK.value, True, ["new_to_precheck"],
                      actions=[JourneyActionType.VERIFY_STATE.value, JourneyActionType.VERIFY_SETTINGS.value])

    if cur_eff == FleetState.PRECHECK.value:
        if evidence.get("precheck_ok") is False:
            missing.append("precheck_ok")
            return decide(cur, False, ["precheck_blocked"], missing=missing,
                          actions=[JourneyActionType.VERIFY_STATE.value, JourneyActionType.CHECK_EVIDENCE.value])
        return decide(FleetState.QR_WAITING.value, True, ["precheck_to_qr_waiting"],
                      actions=[JourneyActionType.WAIT.value, JourneyActionType.VERIFY_STATE.value])

    if cur_eff == FleetState.QR_WAITING.value:
        started = _as_dt(evidence.get("journey_started_at") or evidence.get("registered_at"))
        hrs = _hours_since(started, now)
        if hrs is None:
            missing.append("registered_at_or_journey_started_at")
            return decide(cur, False, ["qr_wait_missing_start"], missing=missing,
                          actions=[JourneyActionType.WAIT.value])
        if hrs < qr_wait_h:
            wait = int((qr_wait_h - hrs) * 3600)
            return decide(cur, False, ["qr_wait_incomplete"], wait=wait,
                          actions=[JourneyActionType.WAIT.value])
        return decide(FleetState.READY_TO_LINK.value, True, ["qr_wait_complete"],
                      actions=[JourneyActionType.VERIFY_STATE.value])

    if cur_eff == FleetState.READY_TO_LINK.value:
        if live != "authorized" and not evidence.get("linked"):
            missing.append("authorized_or_linked")
            return decide(cur, False, ["awaiting_link"], missing=missing,
                          actions=[JourneyActionType.VERIFY_STATE.value])
        return decide(FleetState.AUTHORIZED_QUIET.value, True, ["linked_to_quiet"],
                      actions=[JourneyActionType.VERIFY_STATE.value, JourneyActionType.CHECK_WEBHOOK.value])

    if cur_eff == FleetState.AUTHORIZED_QUIET.value:
        if live and live != "authorized":
            missing.append("live_authorized")
            return decide(cur, False, ["quiet_requires_authorized"], missing=missing,
                          actions=[JourneyActionType.VERIFY_STATE.value])
        linked_at = _as_dt(evidence.get("linked_at") or evidence.get("authorized_at"))
        hrs = _hours_since(linked_at, now)
        if hrs is not None and hrs < quiet_min_h:
            wait = int((quiet_min_h - hrs) * 3600)
            return decide(cur, False, ["quiet_window"], wait=wait, actions=[JourneyActionType.WAIT.value])
        # connected_at alone never advances
        if evidence.get("connected_at") and not (
            evidence.get("first_real_inbound_at") or evidence.get("has_real_inbound")
            or evidence.get("allow_quiet_exit_without_inbound")
        ):
            # Still allow move to inbound building to *start* seeking inbound
            return decide(FleetState.INBOUND_BUILDING.value, True, ["quiet_to_inbound_building"],
                          actions=[JourneyActionType.REQUEST_INBOUND.value, JourneyActionType.CHECK_EVIDENCE.value])
        return decide(FleetState.INBOUND_BUILDING.value, True, ["quiet_to_inbound_building"],
                      actions=[JourneyActionType.REQUEST_INBOUND.value])

    if cur_eff == FleetState.INBOUND_BUILDING.value:
        if not (evidence.get("first_real_inbound_at") or evidence.get("has_real_inbound")
                or (evidence.get("real_inbound_count") or 0) > 0):
            missing.append("first_real_inbound")
            return decide(cur, False, ["inbound_evidence_missing"], missing=missing,
                          actions=[JourneyActionType.REQUEST_INBOUND.value, JourneyActionType.CHECK_EVIDENCE.value])
        # connected_at-only graduation forbidden
        if evidence.get("connected_at_only_claim"):
            return decide(cur, False, ["connected_at_alone_insufficient"], missing=["real_activity"],
                          actions=[JourneyActionType.CHECK_EVIDENCE.value])
        return decide(FleetState.BIDIRECTIONAL_BUILDING.value, True, ["inbound_to_bidirectional"],
                      actions=[JourneyActionType.PREPARE_REPLY.value, JourneyActionType.CHECK_EVIDENCE.value])

    if cur_eff == FleetState.BIDIRECTIONAL_BUILDING.value:
        has_out = evidence.get("first_real_outbound_at") or evidence.get("has_real_outbound") \
            or (evidence.get("real_outbound_count") or 0) > 0
        has_bi = evidence.get("bidirectional_chats") or evidence.get("has_bidirectional")
        if not has_out and not has_bi:
            missing.append("real_outbound_or_bidirectional")
            return decide(cur, False, ["bidirectional_evidence_missing"], missing=missing,
                          actions=[JourneyActionType.PREPARE_REPLY.value, JourneyActionType.CHECK_EVIDENCE.value])
        return decide(FleetState.CONTROLLED_RAMP.value, True, ["bidirectional_to_ramp"],
                      actions=[JourneyActionType.CHECK_EVIDENCE.value])

    if cur_eff == FleetState.CONTROLLED_RAMP.value:
        curve = settings.get("ramp_curve") or [12, 20, 32, 48, 66, 84, 100]
        day_index = int(evidence.get("ramp_day_index") or evidence.get("days_on_ramp") or 0)
        inbound = int(evidence.get("real_inbound_count") or evidence.get("inbound_today") or 0)
        outbound = int(evidence.get("real_outbound_count") or evidence.get("outbound_today") or 0)
        total_flow = inbound + outbound
        if evidence.get("total_flow") is not None:
            total_flow = int(evidence["total_flow"])
        # Day-10 style: last ramp step or explicit day10 flag → WARMUP_READY
        if evidence.get("day10_complete") or day_index >= max(0, len(curve) - 1):
            return decide(FleetState.WARMUP_READY.value, True, ["day10_to_warmup_ready"],
                          actions=[JourneyActionType.CHECK_EVIDENCE.value])
        target = curve[min(day_index, len(curve) - 1)]
        if total_flow < int(settings.get("total_flow_min", curve[0])):
            # still progressing within ramp, but not day10 yet — stay / reevaluate
            missing.append("total_flow_min")
            return decide(cur, False, ["ramp_flow_below_min"], missing=missing,
                          actions=[JourneyActionType.CHECK_EVIDENCE.value, JourneyActionType.REEVALUATE.value])
        # Mid-ramp: remain CONTROLLED_RAMP until day10
        return decide(cur, False, ["ramp_in_progress", f"target_flow_{target}", f"total_flow_{total_flow}"],
                      actions=[JourneyActionType.CHECK_EVIDENCE.value, JourneyActionType.REEVALUATE.value])

    return decide(cur, False, ["no_transition"], actions=[JourneyActionType.REEVALUATE.value])


def make_idempotency_key(account_id: str, journey_id: str, action_type: str, scheduled_slot: str) -> str:
    return f"{account_id}:{journey_id}:{action_type}:{scheduled_slot}"
