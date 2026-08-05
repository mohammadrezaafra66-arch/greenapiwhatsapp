# V67.1 Phase 1 — Implementation Report

**Branch:** `feature/v67-autonomous-fleet-manager`  
**Mode:** Implementation (critical safety only)  
**DDL:** ZERO (no `fleet_accounts`, no Alembic apply)

## Approved Decision IDs (exact Recommended preserved)

| ID | Recommended (verbatim) | Status |
|---|---|---|
| D-H1 | Hybrid WRAP; mesh default OFF for new Autopilot journeys; existing enrollments continue until cutover; deprecate after canary | APPROVED — OWNER ACCEPTED RECOMMENDED |
| D-H2 | Yes — adopt V67 ladder; grandfather general mesh GRADUATED (≥25) as CAMPAIGN_READY if clean | APPROVED (authority only in Phase 1; no day migration) |
| D-H3 | Yes — bit-identical to current WarmupConfig | APPROVED (Phase 2 seed) |
| D-H4 | Separate `fleet_accounts` | APPROVED (Phase 2) |
| D-H5 | Yes | APPROVED (Phase 2 Alembic) |
| D-C1 | Coexist then unify to 24h | APPROVED — fleet 24h + mesh 48h coexist |
| D-C3 | AFM fail-closed; legacy campaign fail-open until canary then closed | APPROVED; Phase 1 executes “then closed” for campaign lock |
| D-C4 | Operator attestation required for CONSERVATIVE; never auto from Green API addContact | APPROVED (Phase 7) |
| D-C9 | Yes — do not pile Phase 1 onto unpushed main drift blindly | APPROVED — branch created |

## Changed paths

### New
- `backend/app/services/fleet_breaker.py`
- `backend/app/services/campaign_lock.py`
- `backend/app/services/activity_evidence.py`
- `backend/tests/test_v67_phase1_safety.py`
- `docs/v67/11-phase1-implementation-report.md` (this file)
- `docs/v67/12-phase1-test-matrix.md`
- `docs/v67/13-phase1-runtime-safety-map.md`
- `docs/v67/14-phase2-readiness.md`

### Modified
- `backend/app/services/incident_handler.py` — blocked / forced_logout / notAuthorized / device_restriction / auth_churn; suspension notifies fleet breaker
- `backend/app/services/send_gate.py` — `is_account_send_eligible`, `is_account_send_eligible_async`, `gate_check_automated`
- `backend/app/services/campaign_runner.py` — fail-closed CampaignLock; fleet breaker; automated eligibility on deliver
- `backend/app/services/group_campaign_runner.py` — `gate_check_automated`
- `backend/app/services/warmup_engine.py` — mesh autochat flag + automated eligibility
- `backend/app/services/warmup_helper_engine.py` / `warmup_cold_reply.py` — TC send eligibility
- `backend/app/api/v1/webhook.py` — incident recording on blocked / notAuthorized / device restriction
- `backend/app/config.py` — `mesh_autochat_enabled=False`, `campaign_lock_fail_closed=True`
- `backend/tests/test_campaign_lock.py`, `test_v27_part1.py`, `test_v60_step0_parallel_brakes.py`

## Reused components (no parallel engines)

`send_gate`, `GreenAPIClient`, webhook handlers, `incident_handler`, `campaign_runner`, FanOutGuard, TC helpers, mesh (WRAP), Celery, Redis, `volume_guard`, `send_metrics`, `price_service`.

## Incident mapping

| Signal | Incident type | Idempotent |
|---|---|---|
| suspended | `suspended` | open-row |
| blocked | `blocked` | open-row |
| unexpected notAuthorized (was active) | `forced_logout` + `notAuthorized` | open-row |
| auth churn (≥3 auth-loss / 24h) | `auth_churn` | open-row |
| device restriction (detectable payload) | `device_restriction` | open-row |
| yellowCard | existing | unchanged |

`suspendedUntil` still from `getWaSettings` via `refresh_suspended_until` (no live settings mutation).

## Eligibility rules (`is_account_send_eligible`)

Reject: fleet breaker, unresolved critical incident, unknown live state (automated), device-restriction-like live state, plus all `can_send_now` refusals (not active, connect cooldown, cooldown, throttle, blocking live states).

## Breaker semantics (D-C1)

- Trigger: **2 distinct account IDs** with suspension markers in rolling **24h**
- Duplicate suspension for same account: refresh TTL, no extra distinct count
- Fail-closed if Redis unavailable (`is_tripped` → True)
- Manual reset only (`manual_reset`); incident history preserved
- Coexists with mesh 48h killswitch (unchanged)

## Redis campaign lock

- Ownership token; owner-only release (Lua)
- TTL 4h; heartbeat renew helper
- Redis down / acquire error → **no send** + pause reason
- Applied to sequential + parallel campaign entrypoints

## Activity evidence (ZERO DDL)

Computed from existing tables via `activity_evidence.py`.  
`connected_at` / calendar age **not** used as maturity proof.  
Proposed Phase 2 DDL (not applied): optional cached columns on `fleet_accounts` — see `14-phase2-readiness.md`.

## Mesh / TC (D-H1)

- `MESH_AUTOCHAT_ENABLED` / `mesh_autochat_enabled` default **False**
- Existing enrollment rows untouched; automated mesh sends skipped with `mesh_autochat_disabled`
- TC helpers KEEP; all automated sends through gate

## Prohibitions honored

No `fleet_accounts`, Policy DB, Journey/Trust/Risk/Capacity engines, Device Registry, Autopilot, Shadow/Canary, live Green API settings changes, legacy deletion.

## Side-effect proof

All Phase 1 tests use mocks/fakes. No real `sendMessage`, campaign start, warm-up enrollment, Green API `setSettings`, account mutation, queue clear, or live DDL in test paths. Yellow-card handler’s queue clear path was **not** newly expanded (pre-existing).

## Test results (recorded)

| Suite | Result |
|---|---|
| `tests/test_v67_phase1_safety.py` + `test_campaign_lock.py` | **26 passed** |
| Full Backend `pytest tests/` (once) | **1684 passed, 0 failed** (2026-08-05) |
| Baseline failures | **none** |

## Live-state policy (Phase 1)

`gate_check_automated` uses `settings.automated_require_live_state` default **False**: hydrate `InstanceLiveState` when present; otherwise classic `can_send_now`. Strict unknown rejection remains available via `is_account_send_eligible(..., require_live_state=True)` and is unit-tested.

## Acceptance

All Phase 1 acceptance checklist items met. STOP — wait for **Execute V67.1 Phase 2**.
