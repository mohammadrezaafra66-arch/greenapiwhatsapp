# V67.1 — Daily Observation CLI

## Command

```bash
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format persian-text
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format json
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format markdown
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format text
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --show-evidence --strict
```

Default format: `persian-text`.

Session: `--session session-2` only.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | PASS |
| 2 | invalid date |
| 3 | database unavailable / unhealthy |
| 10 | REVIEW_REQUIRED |
| 11 | INSUFFICIENT_EVIDENCE |
| 12 | FAIL |
| 13 | NOT_APPLICABLE |
| 1 | other error |

## Properties

- Reader only — no enable/disable/start/stop/persist/cutover/send options  
- Uses `DailyObservationReportService` — no parallel SQL in CLI  
- No Green API, no Celery task dispatch, no DB writes  

## Typical ENV-A execution

```bash
docker exec claudegreenapi-backend-1 python -m app.scripts.fleet_shadow_daily_report --date 2026-08-06
```
