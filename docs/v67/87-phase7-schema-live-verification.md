# V67.1 Phase 7.3 — Schema Live Verification (ENV-A)

| Check | Result |
|---|---|
| Alembic current | `v67_07_fleet_shadow_snapshots (head)` |
| Heads | Single head |
| Table | `fleet_shadow_snapshots` exists |
| CHECKs | mismatch classes, severity, threshold UNRATIFIED only, simulation_only TRUE, mutates_runtime FALSE, executes FALSE |
| UNIQUE | `uq_fleet_shadow_snapshots_idempotency` |
| Indexes | account/fleet observed, mismatch, severity, run_id, policy_version, threshold, HIGH/CRITICAL partial |
| Migration reapplied | No |

No schema drift vs Phase 7 migration.
