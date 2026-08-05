# V67.1 Phase 7.3 — Observation Window Start

## Official start

| Field | Value |
|---|---|
| Status | **DAY 0 / WINDOW STARTED** |
| First valid scheduled snapshot (UTC) | `2026-08-05 18:03:05.304615` |
| Tehran (IRST, UTC+3:30) | `2026-08-05 21:33:05.304615` |
| run_id | `4638ecd8-a3c0-49b5-9ecd-bc74dfc3d5a9` |
| Cohort | Stage A masked `b12dbd81` (1 account) |
| Shadow version | `v67.7.shadow.1` |
| Policy version | `1` (CONSERVATIVE) |
| Migration | `v67_07_fleet_shadow_snapshots` |
| Schedule | 300 seconds |
| Initial mismatch | `RUNTIME_UNKNOWN` |
| Initial severity | `HIGH` |
| Threshold | `UNRATIFIED` |
| Storage baseline | 2 CELERY_PERIODIC rows after second slot |
| Git SHA at start recording | `b59bf11` was HEAD when window started; operationalization commits follow |

## Integrity

- Not backdated  
- Manual dry-runs do **not** count as observation days  
- Day 1 begins only after a full valid UTC day under the plan  
- **14-day completion is NOT claimed**

## Daily review

06:00 UTC (09:30 IRST)
