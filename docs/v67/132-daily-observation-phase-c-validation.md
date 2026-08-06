# V67.1 — Phase C Validation Hardening

## Engine

Single `DailyObservationValidator` (Phase A) + evidence inputs from Phase C collector/manifest.

## PASS (all required)

- Periodic + cohort coverage healthy
- Snapshot flags clean; cutover_true_count=0
- Infra healthy (DB/Redis/Worker); Beat/scheduler evidence sufficient for day type
- No blockers / stop-level violations
- Mutation evidence fields not UNKNOWN/INSUFFICIENT
- Static manifest MATCH
- Evidence bundle present and `can_support_daily_pass` consistent with HEALTHY mutation fields
- No HIGH/CRITICAL review findings
- Tick tolerance ratified if gap (currently UNRATIFIED → gap is REVIEW)
- Session 1 excluded; current partial day not counted as full PASS via timeline UI (IN_PROGRESS)

## Production honesty

Attributed mutation ledger is `NOT_OBSERVABLE` → collector sets mutation statuses to `INSUFFICIENT_EVIDENCE` and `can_support_daily_pass=false` → **daily PASS does not issue**.

## Status meanings

- FAIL — cutover, flag violations, unhealthy infra/scheduler, idempotency conflict, SHA MISMATCH
- REVIEW_REQUIRED — HIGH/CRITICAL, runtime unknown, sensor stale, tick gap (with complete mutation evidence)
- INSUFFICIENT_EVIDENCE — missing/unknown critical evidence including mutation attribution gap
- NOT_APPLICABLE — outside Session 2 window
