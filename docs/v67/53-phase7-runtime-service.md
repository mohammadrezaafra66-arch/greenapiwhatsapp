# V67.1 Phase 7 — Runtime Service

**Module:** `app.services.shadow_runtime.ShadowRuntimeService`

Modes: API/CLI run-once (manual dry-run allowed while flag false); Celery periodic (requires both runtime+scheduler flags).

Refuses `cutover=true`. Persist append-only to `fleet_shadow_snapshots`. Uses pure `send_gate` predicates only. Never mutates FleetState/Journey/send_gate/cutover.
