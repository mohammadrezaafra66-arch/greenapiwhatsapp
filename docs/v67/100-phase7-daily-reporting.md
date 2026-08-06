# V67.1 Phase 7.3 — Daily Reporting

**Superseded for logic by Owner Change Phase A** — see `114`–`119`.

## CLI

```bash
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format persian-text
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format json
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format markdown
```

Default format is now `persian-text`. Implementation delegates to `DailyObservationReportService` (`v67.owner.daily-observation.1`).

## Properties

- Read-only aggregation  
- No flag mutation  
- No deletion  
- No Green API / send / campaign / Journey  
- Session 2 bounded  
- Fail-closed validity (`PASS` / `FAIL` / `REVIEW_REQUIRED` / `INSUFFICIENT_EVIDENCE`)  

## Smoke (2026-08-05 historical)

Earlier Stage A smoke (pre-Phase A) recorded snapshots_total=2, RUNTIME_UNKNOWN, REVIEW_REQUIRED-style high/critical review. Re-run CLI after Phase A for current Session 2 days.
