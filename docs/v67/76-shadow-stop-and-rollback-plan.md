# V67.1 Phase 7.2 — Shadow Stop and Rollback Plan

## Immediate stop conditions

Disable Shadow immediately if any of:

- Operational mutation detected outside `fleet_shadow_snapshots`
- Green API send reachable from Shadow path
- Campaign / Journey / FleetState / cutover mutation via Shadow
- `cutover=true` on observed account without refusal
- Unauthorized API access / token leak
- Duplicate snapshot storm
- Redis lock failure pattern / DB error storm
- Scheduler overlap / unbounded runtime
- Stale critical sensors / RUNTIME_UNKNOWN spike beyond policy tolerance
- Storage beyond agreed limit
- Snapshot integrity failure
- P0/P1 defect
- Unexpected performance impact on send latency
- Owner stop command

## Future disable sequence (DO NOT EXECUTE in Phase 7.2)

1. Set `V67_SHADOW_SCHEDULER_ENABLED=false`
2. Set `V67_SHADOW_RUNTIME_ENABLED=false`
3. Restart Backend / workers / Beat as required to reload settings
4. Confirm `task_fleet_shadow_tick` returns skipped
5. Optionally clear `V67_SHADOW_OPERATOR_TOKEN` (503 fail-closed)
6. Leave snapshot table intact for forensics unless owner orders downgrade
7. Optional: `alembic downgrade v67_06_fleet_plan_snapshots` (drops Shadow table only)

## Rollback ownership

Authorized operators per D-SE-10.
