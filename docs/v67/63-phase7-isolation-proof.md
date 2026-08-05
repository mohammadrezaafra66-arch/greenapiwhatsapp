# V67.1 Phase 7.1 — Isolation Proof

## Claim

Shadow Runtime is observational only: no live send, no operational mutation, flags OFF by default.

## Call-graph order (ShadowRuntimeService.run_account / _evaluate)

1. Optional flag gate (`require_runtime_flag`)
2. Optional per-account Redis lock
3. Account + FleetAccount lookup
4. `cutover=true` → refuse
5. Policy lookup (default / conservative)
6. Non-mutating scoring (`persist=False`)
7. Journey **preview** only
8. Capacity / budget / eligibility pure engines
9. Legacy eligibility via `is_account_send_eligible` / `can_send_now` (read-only predicates; no send)
10. Freshness evaluation
11. Pure comparison engine
12. Optional persist to `fleet_shadow_snapshots` only (when persist && !dry_run && persistence flag)
13. Return result

## Forbidden targets (evidence)

| Target | Evidence |
|---|---|
| Green API send | No `sendMessage` / `green_api` in shadow_runtime/comparison sources |
| send_gate send execution | Shadow imports eligibility helpers only; send_gate has no Shadow reverse dependency |
| Campaign / group / Mesh / Team Collab send | Not imported by Shadow modules |
| Journey action executor | Uses `JourneyOrchestrator.preview` only |
| Cutover setter | Cutover asserted false; API refuses cutover accounts; no setter |
| Flag toggle API | Status reports flags; no enable endpoint |
| Operational tables | Dry-run: `db.add` not called; persist path only constructs `FleetShadowSnapshot` |

## Idempotency / lock

- Key: `account:shadow_version:policy_version:slot:source`
- Duplicate: pre-select + UNIQUE + savepoint IntegrityError recovery (batch-safe)
- Lock: `fleet:shadow:lock:{account_id}` SET NX + owner token Lua release; fail-closed on Redis error

## Feature flags

- `v67_shadow_runtime_enabled=false` (default)
- `v67_shadow_scheduler_enabled=false` (default)
- Celery task returns no-op before loading accounts when either false
- Beat registration ≠ operational enablement

## Metrics / retention

- In-process counters only; no action triggers
- No automatic Shadow retention/deletion worker

## Verdict

Isolation **VERIFIED** for Phase 7 implementation acceptance.
Live enablement remains a separate gate.
