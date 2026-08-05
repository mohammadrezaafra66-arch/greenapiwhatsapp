# V67.1 Phase 4 — Graduation Trial Framework

**Module:** `app.services.graduation_trial.GraduationTrialFramework`

## Path (recommendation only)

`WARMUP_READY` → (eligible) recommend `GRADUATION_TRIAL`

`applies_fleet_state=False` always in Phase 4.

## Requirements (configurable via policy)

- min trust score (default 55)
- max risk level NORMAL/LOW
- incident_free_days ≥ 7
- bidirectional chats ≥ 2
- day10 complete

Never recommends CAMPAIGN_READY or MATURE as applied state.

## Readiness labels

`NOT_READY` | `READY_FOR_TRIAL` | informational `READY_FOR_CAMPAIGN` / `READY_FOR_MATURE` only with explicit future-path inject flags (not applied).
