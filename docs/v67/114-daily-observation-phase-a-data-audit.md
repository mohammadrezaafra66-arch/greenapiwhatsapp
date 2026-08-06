# V67.1 — Daily Observation Phase A Data Audit

**Owner Change:** Read-Only Daily Observation Report — Phase A  
**Not Phase 8. Not Phase 11.**

## Identity

This audit maps existing sources for a versioned daily report contract. No schema changes. No new API. No Frontend.

## Sources

### fleet_shadow_snapshots (primary)

- **SoT:** Postgres table / ORM `FleetShadowSnapshot`
- **Method:** day-bounded SQL (`observed_at >= start AND observed_at < end`) intersected with Session 2 start
- **Freshness:** written by Celery periodic tick (~300s) and optional manual CLI/API runs
- **Reliability:** high for counts/class/severity/flags; CHECK constraints enforce simulation invariants
- **Historical compare:** yes (previous UTC day count)
- **PASS proof:** can support tick/coverage/mismatch evidence; cannot alone prove global non-mutation
- **Side effects:** read-only SELECT

Indexes used: composites including `observed_at` (account/mismatch/severity), partial HIGH/CRITICAL, unique idempotency. No bare `observed_at`-only index — acceptable at Stage A volume; not a Phase A migration HARD STOP.

### fleet_accounts

- **SoT:** enrolled fleet rows; cohort = `cutover=false` (no cohort column)
- **Method:** `SELECT account_id FROM fleet_accounts WHERE cutover=false`; cutover count separate
- **Reliability:** high for cutover flag
- **Side effects:** none

### Application config flags

- `v67_shadow_runtime_enabled`, `v67_shadow_scheduler_enabled`
- Reliability: config truth, not process health
- Alone cannot prove scheduler HEALTHY

### Celery beat schedule

- `celery_app` beat entry `fleet-shadow-tick` schedule `300.0`
- Mirrored as `PERIODIC_TICK_INTERVAL_SECONDS` in aggregation layer; tested against Beat config

### Infrastructure probes (reuse `/health/detailed` patterns)

- DB: `SELECT 1`
- Redis: `ping()` via `redis_rate_limiter.get_redis`
- Celery workers: `control.ping(timeout=1)`
- Beat: **no dedicated probe** → inferred from recent `CELERY_PERIODIC` snapshots or `UNKNOWN`
- Reliability: point-in-time; UNKNOWN/UNHEALTHY fail-closed

### Shadow in-process metrics

- `shadow_metrics.snapshot()` — best-effort, not fleet-global → optional counts only

### Mutation / send / campaign / Journey / FleetState / send_gate

- **Runtime daily ledger:** not available as trusted SoT
- **Status in report:** `INSUFFICIENT_EVIDENCE`
- Static isolation tests exist but are **static_test_evidence**, not daily runtime proof
- Must not imply PASS from absence of errors

### Session boundary

- Logical Session 2 start from ops doc `107`: `2026-08-05T19:13:46.331651Z`
- Not a DB entity; all queries lower-bounded by this timestamp
- Session 1 excluded

## Explicitly untrusted for PASS

- Absence of errors in logs
- In-process metrics alone
- Flag true without recent periodic snapshot
- Static tests alone for daily operational non-mutation
- Day index ≥ 14

## Existing partial CLI

`fleet_shadow_daily_report.py` (pre-Phase A) aggregated a subset; Phase A replaces its logic with `DailyObservationReportService` while keeping the module path.
