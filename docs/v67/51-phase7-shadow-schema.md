# V67.1 Phase 7 — Shadow Schema

**Revision:** `v67_07_fleet_shadow_snapshots`  
**Table:** `fleet_shadow_snapshots`  
**Revises:** `v67_06_fleet_plan_snapshots`

Additive reversible. CHECK constraints force `simulation_only=true`, `mutates_runtime=false`, `executes=false`, `dangerous_threshold_status=UNRATIFIED`. Unique `idempotency_key`. Indexes on account/fleet_account/mismatch/severity/run_id/policy_version/threshold + partial HIGH/CRITICAL.
