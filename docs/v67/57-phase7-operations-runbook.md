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

## Future approved enablement (NOT Phase 7 / 7.1 / 7.2)

Phase 7.2 completed **preflight only** (`docs/v67/65`–`83`). Flags must stay false until owner answers D-SE-01+ and issues a separate named-environment authorization.

1. Owner answers `docs/v67/82-shadow-enablement-owner-decisions.md`
2. Separate authorization for the exact named environment
3. Set operator token + flags only as authorized
4. Verify scheduler health and snapshot production
5. Start 14-day observation window only by separate command
6. Immediate disable: set both flags false (see `76`)

## Dangerous threshold

`dangerous_mismatch_threshold_status=UNRATIFIED` — compute/display only; no operational reaction.

## Rollback

Disable flags; alembic downgrade to `v67_06` drops only `fleet_shadow_snapshots`.
