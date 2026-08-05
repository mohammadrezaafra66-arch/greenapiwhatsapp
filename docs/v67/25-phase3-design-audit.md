# V67.1 Phase 3 — Design Audit (read-only)

**Date:** 2026-08-05  
**Branch:** `feature/v67-autonomous-fleet-manager`  
**Mode:** Design only before implementation  
**Owner design locks (authoritative):**

1. `fleet_accounts.fleet_state` canonical  
2. Legacy states = sensors  
3. `send_gate` sole runtime send authority  
4. FleetState must **not** grant/deny real sending  
5. SIMULATION + SHADOW only  
6. Legacy runtime unchanged  
7. No dual-write to WarmupState  
8. Deterministic / policy-driven / auditable / idempotent transitions  
9. Major incidents override progress  
10. Day 10 / GRADUATED → WARMUP_READY only  
11. No CAMPAIGN_READY without Graduation Trial (later)  
12. No MATURE in Phase 3  
13. Trust/Risk/Capacity = interfaces only  
14. No real enrollment/scheduling  

---

## 1. Reusable code

| Component | Path | Phase 3 use |
|---|---|---|
| FleetAccount / FleetPolicy | `models/fleet_*` | Load + snapshot policy |
| FleetState enum / matrix | `services/fleet_state.py` | Canonical states |
| FleetStateAdapter | `services/fleet_state_adapter.py` | Sensor recommend + shadow compare |
| fleet_seed / policy defaults | `services/fleet_seed.py`, `fleet_policy_defaults.py` | Snapshot seed; validate flow metric |
| activity_evidence | `services/activity_evidence.py` | Evidence gates (reuse, no fork) |
| incident_handler / AccountIncident | existing | Sensor input |
| fleet_breaker | `services/fleet_breaker.py` | Sensor input (read only) |
| send_gate | `services/send_gate.py` | **Do not modify**; prove unchanged |
| Alembic chain | `v67_01`…`v67_03` | Extend with `v67_04` journeys |
| Phase 2 fleet API | `api/v1/fleet.py` | Extend read-only + simulate |

## 2. Missing components (to build)

- `account_journeys` + `journey_actions` tables/migrations  
- Journey domain enums + TransitionDecision VO  
- Pure `evaluate_transition(...)` engine (no IO)  
- Simulation/Shadow orchestrator  
- Shadow comparison classifier  
- Simulation CLI  
- Trust/Risk/Capacity **Protocol/ABC stubs only** (no scoring)

## 3. Transition authority

| Layer | Authority |
|---|---|
| Pure engine | Recommends next state + actions |
| Orchestrator (SIM/SHADOW) | Persists evaluation / planned sim actions; **never** sets cutover |
| FleetAccount.fleet_state mutation | Only when `persist_simulation` on explicit sim fixtures OR never for prod-like (`cutover` stays false) |
| send_gate | Unchanged — real send veto |

## 4. Transaction / locking / idempotency

| Concern | Strategy |
|---|---|
| Transaction | Single AsyncSession; flush journey + actions together |
| Active journey uniqueness | Partial unique index: one row per `fleet_account_id` where `status IN ('ACTIVE','PAUSED','SIMULATING')` |
| Action idempotency | UNIQUE `idempotency_key` = `{account_id}:{journey_id}:{action_type}:{scheduled_slot}` |
| Optimistic concurrency | `account_journeys.version` increment on state change |
| Redis lock | Not required for Phase 3 sim (no live claim) |

## 5. Shadow-mode boundary

- Compare: canonical FleetState vs adapter vs journey engine vs AccountStatus vs WarmupState vs live vs incidents  
- Labels: MATCH / SAFE_MISMATCH / DANGEROUS_MISMATCH / INSUFFICIENT_EVIDENCE  
- **No automatic repair**

## 6. No-cutover proof plan

- Orchestrator never writes `cutover=True`  
- Tests assert `cutover is False` after simulate  
- `send_gate` source must not reference FleetState / journeys  
- Action types exclude SEND_*  

## 7. Proposed migration

`v67_04_account_journeys` → creates `account_journeys` + `journey_actions` (additive, IF NOT EXISTS, downgrade drops both).

## 8. API auth note

Project APIs historically have **no global RBAC**. Phase 3 follows existing `/api/v1/fleet` convention. Documented; no invented auth system. Rate-limit: best-effort in-process counter on simulate endpoint (optional soft limit).

## 9. Hard-stop checks

| Check | Result |
|---|---|
| Must change send_gate? | **No** |
| FleetState semantics vs matrix? | **Aligned** |
| Tx/lock strategy clear? | **Yes** |
| Journey schema conflict? | **No** (`account_journeys` free) |
| Auto real account mutation? | **Forbidden by design** |
| Green API live mutation? | **Forbidden** |

**Verdict: Phase 3 may proceed.**
