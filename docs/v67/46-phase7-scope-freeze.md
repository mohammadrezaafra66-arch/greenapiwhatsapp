# V67.1 Phase 7 — Scope Freeze

**Status:** Scope **RATIFIED** by D-P7-01…16 (`47-phase7-owner-decisions.md`).  
**Implementation:** NOT started — wait for explicit `Execute V67.1 Phase 7`.  
**Execution Phase 7 name:** Shadow Runtime / Continuous Comparison / Drift Detection / Operator Visibility (authenticated)

**Master Architecture note:** Master `فاز ۷` is Human/Native Contacts; Master `فاز ۱۲` covers Simulation/Shadow/Canary. Per **D-P7-01** and **D-P7-15**, execution Phase 7 is Shadow-only; Human/Native Contacts is a **separate** controlled phase after Shadow and before Canary. This freeze does not renumber Master.

## Exact objective

Build an observational Shadow Runtime that:

- reads production-like sensors
- runs V67 engines in parallel with legacy diagnostics
- compares outputs and classifies drift
- persists explainable rows in `fleet_shadow_snapshots` (D-P7-09)
- exposes **authenticated** operator APIs (D-P7-16)
- never changes runtime behavior

## Explicitly IN scope (when owner says `Execute V67.1 Phase 7`)

- ShadowRuntimeService (read → evaluate → compare → snapshot)
- ShadowComparisonEngine mismatch taxonomy
- Dedicated table `fleet_shadow_snapshots` (additive, reversible)
- Celery periodic Shadow task with `v67_shadow_runtime_enabled=false` default (D-P7-08); flag stays disabled through Phase 7 implementation/tests
- CLI/API run-once for controlled testing
- Policy field for dangerous-mismatch threshold in **UNRATIFIED** state (D-P7-11); rates computed/displayed; no live reaction
- Auth/RBAC on all Shadow routes including read-only (D-P7-16)

## Explicitly OUT of scope (forbidden in Phase 7)

| Item | Verdict | Decision |
|---|---|---|
| Live Journey execution | FORBIDDEN | D-P7-02 |
| Autopilot | FORBIDDEN | freeze |
| Live campaign / send | FORBIDDEN | D-P7-07 |
| Green API mutation / send | FORBIDDEN | freeze |
| Celery send/campaign enqueue | FORBIDDEN | D-P7-07/08 |
| `send_gate` / FleetState live send authority | FORBIDDEN — sole authority stays `send_gate` | D-P7-03 |
| Eligibility as operational grant | FORBIDDEN — recommendation/compare/Shadow only | D-P7-04 |
| `fleet_accounts.cutover=true` | FORBIDDEN — must remain false; no setter surface | D-P7-05 |
| Canary | DEFERRED | D-P7-06 |
| Real campaign execution bridge | FORBIDDEN | D-P7-07 |
| Human/Native Contacts implementation | FORBIDDEN in Phase 7 | D-P7-01/15 |
| Numeric dangerous-mismatch activation | FORBIDDEN until later owner decision | D-P7-11 |
| Legacy removal / production activation | FORBIDDEN | freeze |
| Unauthenticated Shadow APIs | FORBIDDEN | D-P7-16 |

## Authority model

- Legacy runtime remains authoritative.
- V67 Shadow is observational only.
- `send_gate` unchanged and sole send authority (D-P7-03).
- FleetState does **not** influence live send decisions in Phase 7.
- Eligibility remains recommendation/comparison/Shadow-only (D-P7-04).
- Phase 6.1 fail-closed rules retained: High Volume = `READY_FOR_MATURE` only (D-P7-12); Journey `COMPLETED` and missing Journey fail-closed (D-P7-13/14).

## Allowed writes

- `fleet_shadow_snapshots` only (`simulation_only=true`, `mutates_runtime=false`, `executes=false`)
- Structured logs / metrics for shadow runs

## Prohibited writes

AccountStatus, WarmupState, FleetState, Journey, Campaign, Queue, Green API, send counters, breaker trips, incident mutations, cutover flag from shadow path.

## Isolation / rollback

- Global flag OFF by default; remains OFF after implementation (D-P7-08)
- Per-account: FleetAccount exists, `cutover=false`, sensors readable
- Redis lock, fail-closed, idempotent, no overlap, no burst catch-up
- Rollback = keep/disable flag; snapshots remain inert

## Observation window (D-P7-10)

**14 full consecutive days** before Canary discussion may begin — only after explicit enable in an approved environment, healthy scheduler, successful snapshots, and no unresolved P0/P1 Shadow defects. Implementation/tests do not count.

## Comparison / drift (design)

Mismatch classes: MATCH, SAFE_MISMATCH, DANGEROUS_MISMATCH, INSUFFICIENT_EVIDENCE, LEGACY_MORE_PERMISSIVE, V67_MORE_PERMISSIVE, POLICY_VERSION_MISMATCH, SENSOR_STALE, RUNTIME_UNKNOWN  

Severity: INFO / LOW / MEDIUM / HIGH / CRITICAL — policy-driven; numeric dangerous threshold **UNRATIFIED** until separate owner decision (D-P7-11).

## Post-Shadow sequence (D-P7-15)

1. Phase 7 — Shadow Runtime  
2. Human/Native Contacts phase  
3. Shadow validation including contact/compliance evidence  
4. Canary readiness  
5. Canary only after explicit owner authorization  

## Success criteria (when implemented)

- Deterministic, explainable, idempotent shadow runs
- Auth on all Shadow APIs
- Zero runtime mutation proofs in tests (including cutover remains false)
- Full backend green
- No Canary/Cutover/Human-Contacts/live-send leakage
- Flag remains disabled through Phase 7 ship
