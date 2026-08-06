# V67.1 — Daily Observation Correlation Design

## Goal

Correlate Shadow runs for a UTC day without migration and without behavior change.

## Reused fields (existing snapshot columns)

- run_id, account_id (masked in owner payload), source, observed_at
- shadow_version, policy_version, mismatch_class, severity, idempotency_key

## Logging enrichment (no behavior change)

`shadow_run_complete` now also logs `policy_version`, `idempotency_key`, `slot` (scheduled_slot).

`out` dict includes `scheduled_slot` for structured context.

## Collector

Bounded `LIMIT 12` sample from periodic snapshots for the day. No unbounded log scan.

## Gaps remaining

- Celery task id not persisted on snapshot rows (NOT_OBSERVABLE historically without migration)
- Redis lock result not day-ledgered
- Deployed SHA at run time not stored per snapshot (release-level manifest only)

## Verdict

Correlation is **sufficient for observational reporting** via snapshot columns + sample. Gaps are recorded honestly; no migration introduced.
