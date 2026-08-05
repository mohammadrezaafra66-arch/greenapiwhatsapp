# V67.1 Phase 7 — Operations Runbook

## Feature flags (remain OFF after Phase 7 ship)

- `V67_SHADOW_RUNTIME_ENABLED=false`
- `V67_SHADOW_SCHEDULER_ENABLED=false`
- `V67_SHADOW_OPERATOR_TOKEN=<set before any Shadow API use>`
- `V67_SHADOW_OPERATOR_ROLE=operator` (Backend-derived; client cannot self-assign)
- Do **not** send a mismatched `X-Fleet-Shadow-Role` (403 spoof reject)

Phase 7 / 7.1 completion does **not** authorize enabling Shadow in any live environment.

## Manual dry-run

```bash
python -m app.scripts.fleet_shadow_run --account-id <uuid> --dry-run
```

Authenticated API: `POST /api/v1/fleet/shadow/run-once?account_id=...` with Shadow headers.

## Future approved enablement (NOT Phase 7)

1. Separate owner authorization for an approved environment  
2. Set operator token + both flags carefully  
3. Verify scheduler health and snapshot production  
4. Start 14-day observation window (D-P7-10)  
5. Immediate disable: set both flags false  

## Dangerous threshold

`dangerous_mismatch_threshold_status=UNRATIFIED` — compute/display only; no operational reaction.

## Rollback

Disable flags; alembic downgrade to `v67_06` drops only `fleet_shadow_snapshots`.
