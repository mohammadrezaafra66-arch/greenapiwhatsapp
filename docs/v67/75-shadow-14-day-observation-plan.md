# V67.1 Phase 7.2 — 14-Day Shadow Observation Plan (FROZEN DESIGN)

**Status:** Observation **Session 2** `DAY 0 / WINDOW STARTED` on ENV-A (see `107-phase7-session2-recovery-and-day0.md`).

Session 1 official start UTC `2026-08-05 18:03:05.304615` is **INVALID / ARCHIVED** (`106`) — do not count.

Session 2 official start UTC: `2026-08-05 19:13:46.331651` (first CELERY_PERIODIC snapshot).  
Tehran: `2026-08-05 22:43:46.331651` IRST.

Do **not** mark Day 1 until a full valid UTC day elapses.  
Do **not** claim 14-day completion.

## Prerequisites (all required before start)

1. Separate explicit owner command naming ENV-A (or other approved env)
2. D-SE-01…D-SE-11 answered as needed
3. Migration verified/applied
4. Operator token configured Backend-only
5. Redis + Celery + Beat healthy
6. Monitoring accepted as PARTIALLY_SUFFICIENT with daily review
7. Cohort approved; `fleet_accounts` populated for cohort
8. Both flags explicitly authorized
9. No open P0/P1 Shadow defects
10. Full Backend suite green
11. No live execution path from Shadow itself

## Official start

- Condition: owner command after gates PASS
- Timestamp source: first successful periodic tick **or** owner-declared UTC start recorded in ops log
- Timezone: **UTC** for consecutive-day counting
- Consecutive-day rule: 14 calendar days UTC with required daily completeness (see below)
- Invalidates/restarts: emergency stop; >N hours missing ticks (owner-set); P0 defect; operational mutation detection

## Scheduler

- Default code interval: 300s (owner may choose D-SE-08)
- No catch-up storm (implementation skips disabled / uses current slot)

## Daily health review

- Task skip/success counts
- Mismatch class histogram
- HIGH/CRITICAL rows
- Stale / RUNTIME_UNKNOWN spikes
- Redis/DB/Celery errors
- Auth 401/403/503 anomalies
- Storage growth
- Confirm flags still as authorized

## Daily report format (English)

Date (UTC) | ticks expected/actual | accounts covered | by mismatch | HIGH/CRITICAL | incidents | stop-triggers | operator initials

## Stop / rollback

See `76-shadow-stop-and-rollback-plan.md`.

## Final acceptance (after valid 14 days)

- Completeness thresholds met
- No forbidden execution
- Drift review delivered
- Owner checkpoint signed
- **Canary remains deferred** — no Canary discussion as automatic next step

## Phase 7.2

Does **not** start this window.
