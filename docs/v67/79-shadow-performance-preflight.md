# V67.1 Phase 7.2 — Shadow Performance Preflight

## Measurements (fixtures / pure engine)

| Metric | Result |
|---|---|
| Comparison engine 100 calls | **0.62 ms** total (~0.006 ms/call) on Backend container |
| Configured max runtime | `v67_shadow_max_runtime_seconds=120` |
| Batch size | 25 |
| Lock overhead (disposable) | Redis SET NX ~9.55 ms |
| Disabled Celery task | Immediate return (no account load) |

## Design bounds

- Periodic path orders by `account_id`, `LIMIT` batch
- Per-account lock prevents same-account overlap
- Persist uses savepoint for IntegrityError (batch-safe)
- No full-table Shadow load in hot path

## Missing live end-to-end timing

Full one-account `ShadowRuntimeService.run_account` against live DB **not** executed (would touch live sensors/accounts). Fixture dry-run tests cover no-persist path.

## Verdict

**Acceptable for Stage A** from pure-engine and lock latency evidence.  
Re-measure one-account service timing during authorized Stage A dry-run.

## P0/P1 performance defects

None proven in Phase 7.2. No code remediation.
