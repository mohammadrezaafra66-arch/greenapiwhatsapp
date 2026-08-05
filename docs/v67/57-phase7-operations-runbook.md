# V67.1 Phase 7 — Operations Runbook

## Feature flags

Defaults remain false in code. ENV-A Stage A currently runs with both flags **true** after Phase 7.3 gates (see `99`).

Emergency disable:

- `V67_SHADOW_RUNTIME_ENABLED=false`
- `V67_SHADOW_SCHEDULER_ENABLED=false`
- recreate Backend/workers/Beat

Operator token / role:

- `V67_SHADOW_OPERATOR_TOKEN=<Backend-only Secret>`
- `V67_SHADOW_OPERATOR_ROLE=operator` (Backend-derived; client cannot self-assign)
- Do **not** send a mismatched `X-Fleet-Shadow-Role` (403 spoof reject)

Phase 7 / 7.1 / 7.2 completion does **not** by itself finish observation. Phase 7.3 started the ENV-A Stage A observation window (see `99`).

## ENV-A Stage A (active)

- Runtime + scheduler flags: enabled after gated proofs
- Cohort: exactly 1 FleetAccount
- Schedule: 300s
- Daily review: 06:00 UTC
- Emergency stop: set both flags false and recreate Backend/workers/Beat

## Manual dry-run

```bash
python -m app.scripts.fleet_shadow_run --account-id <uuid> --dry-run
```

Authenticated API: `POST /api/v1/fleet/shadow/run-once?account_id=...` with Shadow headers.

## Future notes

Phase 7.3 ratified D-SE decisions and started observation (Day 0). Completion still requires 14 valid consecutive days and a later acceptance audit.

Immediate disable: set both flags false (see `76`).

## Dangerous threshold

`dangerous_mismatch_threshold_status=UNRATIFIED` — compute/display only; no operational reaction.

## Rollback

Disable flags; alembic downgrade to `v67_06` drops only `fleet_shadow_snapshots`.
