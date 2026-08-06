# V67.1 — Automated Daily Observation Reporting

## Task

`tasks.daily_observation_report`

## Schedule

- **06:00 UTC**
- Celery timezone `Asia/Tehran` → crontab `hour=9, minute=30` (09:30 Tehran)

## Behavior

1. Build previous completed UTC day via `DailyObservationReportService` (same engine as CLI/API/UI)
2. Structured log (status, reasons, read_only flags)
3. Optional atomic JSON + Persian Markdown under `/app/var/daily_observation_reports/{date}.*`
4. Path traversal rejected; date-keyed only
5. Idempotent overwrite of same day files
6. soft_time_limit 120s / time_limit 180s
7. Failures logged; no retry chain to send/campaign queues

## Forbidden

- WhatsApp / email / Green API
- Feature flag changes
- Shadow snapshot creation
- Business DB writes
- Session restart
- Task chains

## Queue

Default `celery` queue (maintenance), not `campaigns` / `sending`.
