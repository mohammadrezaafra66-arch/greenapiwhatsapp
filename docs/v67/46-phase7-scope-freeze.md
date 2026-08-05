# V67.1 Phase 7 — Scope Freeze (Design Only)

**Status:** FROZEN as design — **NOT implemented**. Phase 6.1 remediation must complete before any Phase 7 code.  
**Execution Phase 7 name:** Shadow Runtime / Continuous Comparison / Drift Detection / Operator Read-Only Visibility  
**Master Architecture note:** Master `فاز ۷` is Human/Native Contacts; Master `فاز ۱۲` covers Simulation/Shadow/Canary. V67.1 **execution** numbering on this branch places Shadow after Eligibility (Phase 6). This freeze does **not** renumber Master; it records the execution-path Phase 7 as Shadow-only and defers Master Human/Native Contacts to a later owner-approved execution slot.

## Exact objective

Build an observational Shadow Runtime that:

- reads production-like sensors
- runs V67 engines in parallel with legacy diagnostics
- compares outputs and classifies drift
- persists explainable shadow snapshots
- exposes read-only operator APIs

## Explicitly IN scope (when owner says `Execute V67.1 Phase 7`)

- ShadowRuntimeService (read sensors → decide → compare → snapshot)
- ShadowComparisonEngine mismatch taxonomy
- Additive persistence (`fleet_shadow_snapshots` if plan snapshots insufficient)
- Optional Celery periodic task that **only** computes snapshots (flag OFF by default)
- Read-only operator APIs + dry-run CLI
- Feature flag `v67_shadow_runtime_enabled=false` default

## Explicitly OUT of scope (forbidden in Phase 7)

| Item | Verdict |
|---|---|
| Live Journey execution | FORBIDDEN |
| Autopilot | FORBIDDEN |
| Live campaign / send | FORBIDDEN |
| Green API mutation | FORBIDDEN |
| Celery send/campaign enqueue | FORBIDDEN |
| `send_gate` cutover / FleetState send authority | FORBIDDEN — legacy gate remains sole send authority |
| Eligibility as operational grant | FORBIDDEN — recommendation/compare only |
| `fleet_accounts.cutover=true` | FORBIDDEN — must remain false |
| Canary | DEFERRED (Phase 8+ execution) |
| Real campaign execution bridge | DEFERRED |
| Legacy code removal | FORBIDDEN |

## Authority model

- Legacy runtime remains authoritative.
- V67 Shadow is observational only.
- `send_gate` unchanged and sole send authority.
- FleetState does **not** influence live send decisions in Phase 7.
- Eligibility remains recommendation-only.

## Allowed writes

- Shadow snapshot rows only (`simulation_only=true`, `mutates_runtime=false`, `executes=false`)
- Structured logs / metrics for shadow runs

## Prohibited writes

- AccountStatus, WarmupState, FleetState, Journey, Campaign, Queue, Green API, send counters, breaker trips, incident mutations from shadow path

## Isolation / rollback

- Global flag OFF by default
- Per-account: only evaluate when FleetAccount exists, `cutover=false`, sensors readable
- Redis lock, fail-closed, no overlap, no burst catch-up
- Rollback = disable flag; snapshots remain inert

## Comparison / drift (design)

Mismatch classes: MATCH, SAFE_MISMATCH, DANGEROUS_MISMATCH, INSUFFICIENT_EVIDENCE, LEGACY_MORE_PERMISSIVE, V67_MORE_PERMISSIVE, POLICY_VERSION_MISMATCH, SENSOR_STALE, RUNTIME_UNKNOWN  

Severity: INFO / LOW / MEDIUM / HIGH / CRITICAL — **policy-driven thresholds only**.

## Success criteria (when implemented)

- Deterministic, explainable, idempotent shadow runs
- Zero runtime mutation proofs in tests
- Full backend green
- No Canary/Cutover leakage

## Phase 8 handoff

Canary cohort execution remains a later phase after Shadow observation window and owner sign-off.
