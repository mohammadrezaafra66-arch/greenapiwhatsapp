# V67.1 — Daily Observation Validation Rules

**Module:** `DailyObservationValidator` (pure, no I/O)

## Precedence (first hard fail wins)

1. cutover=true  
2. executes violation  
3. mutates_runtime violation  
4. simulation_only violation  
5. missing fleet cohort  
6. zero expected periodic coverage (expected>0 and actual=0)  
7. scheduler unhealthy  
8. database unhealthy  
9. Redis unhealthy  
10. Celery worker unhealthy  
11. idempotency/duplicate violation  

## Soft / evidence rules

- Tick gap with `TICK_TOLERANCE_STATUS=UNRATIFIED` → cannot PASS; REVIEW_REQUIRED if other evidence present  
- HIGH/CRITICAL, RUNTIME_UNKNOWN, SENSOR_STALE, live_state_missing → REVIEW_REQUIRED (when mutation evidence complete)  
- Any infra UNKNOWN or mutation evidence INSUFFICIENT → overall cannot be PASS → `INSUFFICIENT_EVIDENCE`  
- Unknown + review findings → `INSUFFICIENT_EVIDENCE` (honest insufficient wins)  
- NOT_APPLICABLE for pre-Session-2 dates  

## PASS conditions

All hard fails absent; exact tick completeness; cohort covered; infra HEALTHY (DB/Redis/Celery worker/scheduler); safety OK; no HIGH/CRITICAL/runtime-unknown/stale/live_state_missing; mutation evidence fields HEALTHY (injected only when truly available — production aggregator leaves them INSUFFICIENT).

## Production honesty

Live aggregation sets operational mutation evidence to `INSUFFICIENT_EVIDENCE`, so production CLI typically exits `INSUFFICIENT_EVIDENCE` or `REVIEW_REQUIRED`/`FAIL`, not false PASS.
