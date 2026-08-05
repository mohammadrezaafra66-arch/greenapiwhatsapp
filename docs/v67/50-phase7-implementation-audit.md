# V67.1 Phase 7 — Implementation Audit (pre-code)

**Date:** 2026-08-05  
**Branch:** `feature/v67-autonomous-fleet-manager`  
**Ratification:** `b28c8dd` (D-P7-01…16 APPROVED)  
**Mode:** Audit before implementation  

## Preflight

| Check | Result |
|---|---|
| Branch | `feature/v67-autonomous-fleet-manager` |
| Ratification commit | `b28c8dd25cbb6a743f7fc492afa701a431a2899c` |
| Phase 6.1 commits | `ec1ec56`, `386d294`, `095ee97` present |
| Tracked dirty | clean |
| Unrelated untracked | pre-existing research/prompt files only (not staged) |
| Alembic head | `v67_06_fleet_plan_snapshots` |

## Hard-stop review

| Condition | Finding | Resolution |
|---|---|---|
| Shadow requires changing `send_gate` | No — use pure `can_send_now` / `is_account_send_eligible` with injected inputs | Proceed |
| auth/RBAC cannot be enforced | **No existing HTTP auth/RBAC on `/api/v1`** | **Additive Shadow-only operator token** (settings) + fail-closed if unconfigured; not a parallel auth platform; required by D-P7-16 |
| Celery would execute despite flag=false | Beat may register; task must no-op before any work when flags false | Prove with tests |
| Idempotency strategy | Deterministic key + unique constraint + Redis lock | Proceed |
| Shadow reads require mutating ops tables | No — all engines have non-mutating APIs | Proceed |
| Migration vs head | Next revision `v67_07` after `v67_06` | Proceed |
| Legacy comparison identifiable | AccountStatus, WarmupState, pure send eligibility, Phase 3 compare_shadow | Proceed |
| Owner decisions | All D-P7-01…16 honor-able | Proceed |

### Auth strategy (D-P7-16)

Existing app: open `/api/v1` with `Depends(get_db)` only.  
Phase 7 introduces **route-level** dependency:

- Header: `X-Fleet-Shadow-Token` (or `Authorization: Bearer <token>`)
- Settings: `v67_shadow_operator_token` (empty default → Shadow APIs return **503** fail-closed / unconfigured)
- Privileged role claim: `X-Fleet-Shadow-Role` ∈ `v67_shadow_allowed_roles` (default `admin,operator`)
- Unauthenticated → 401; wrong role → 403; token unset → 503

No flag-toggle API. No cutover setter.

## Reusable components

| Component | Use |
|---|---|
| FleetStateAdapter.derive | adapter recommendation |
| JourneyOrchestrator.preview | journey recommendation + Phase 3 shadow bits |
| journey_shadow.compare_shadow | input to broader Phase 7 taxonomy |
| FleetScoringService.simulate(persist=False) | trust/risk/readiness/evidence |
| CapacityPlanner / FleetBudgetEngine | capacity/budget |
| CampaignEligibilityEngine.decide | eligibility v2 |
| fleet_breaker.is_tripped(fail_closed=False) | read breaker |
| send_gate.can_send_now / is_account_send_eligible | pure legacy eligibility |
| CampaignLock / Redis SET NX | pattern for per-account shadow lock |

## Shadow read graph

Account → FleetAccount (assert cutover=false) → Policy → evidence/scoring → adapter → journey preview → capacity/budget → eligibility → breaker → live cache (read) → pure send eligibility → freshness → ShadowComparisonEngine → optional persist `fleet_shadow_snapshots`.

## Legacy observation sources

- `accounts.status`, warmup state fields  
- `can_send_now` / `is_account_send_eligible` (injected live/breaker/critical)  
- Instance live cache via `get_cached_live_state` (no hydrate mutation preferred; DB read of InstanceLiveState allowed without `update_live_state`)

## V67 evaluation graph

Adapter → Journey preview → Trust/Risk/Readiness → Capacity → Budget → Eligibility (v67.6.eligibility.2) → Comparison.

## Transaction / lock / idempotency

- Append-only insert into `fleet_shadow_snapshots`  
- Idempotency key: `{account_id}:{shadow_version}:{policy_version}:{slot}:{source}`  
- Redis lock: `fleet:shadow:lock:{account_id}` TTL from settings; fail-closed for periodic task if Redis down  
- No catch-up of missed slots  

## Feature flags (defaults)

| Flag | Default |
|---|---|
| `v67_shadow_runtime_enabled` | `false` |
| `v67_shadow_scheduler_enabled` | `false` |
| `v67_shadow_persistence_enabled` | `true` (persist still requires explicit run-once persist + privilege; periodic still gated by runtime+scheduler flags) |
| `v67_shadow_batch_size` | `25` |
| `v67_shadow_lock_ttl_seconds` | `60` |
| `v67_shadow_max_runtime_seconds` | `120` |

Periodic task: if either runtime or scheduler flag false → immediate no-op (no evaluate, no write).

## Persistence

Dedicated `fleet_shadow_snapshots` (D-P7-09). Not `fleet_plan_snapshots`.

## Drift taxonomy

MATCH, SAFE_MISMATCH, DANGEROUS_MISMATCH, INSUFFICIENT_EVIDENCE, LEGACY_MORE_PERMISSIVE, V67_MORE_PERMISSIVE, POLICY_VERSION_MISMATCH, SENSOR_STALE, RUNTIME_UNKNOWN  

Severity: INFO…CRITICAL. Threshold status: **UNRATIFIED** only (D-P7-11).

## Freshness

Policy `shadow_freshness` windows; missing freshness policy → fail closed → SENSOR_STALE / INSUFFICIENT_EVIDENCE. Never MATCH on stale critical sensors.

## Rollback

Disable flags; downgrade drops `fleet_shadow_snapshots` only; operational data untouched.

## Proposed tests

Unit comparison; service flag no-op; migration up/down/re-up; API 401/403/503; CLI; Celery disabled; isolation (send_gate unchanged, cutover false, no Green API).

## Audit verdict

**PROCEED** with Shadow-scoped operator-token auth (documented exception to “reuse existing RBAC” because none exists; required by D-P7-16).
