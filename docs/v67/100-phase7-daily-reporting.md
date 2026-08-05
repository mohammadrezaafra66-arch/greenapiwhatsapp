# V67.1 Phase 7.3 — Daily Reporting

## CLI

```bash
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD
python -m app.scripts.fleet_shadow_daily_report --date YYYY-MM-DD --format markdown
```

## Properties

- Read-only SQL  
- No flag mutation  
- No deletion  
- No Green API / send / campaign / Journey  
- JSON or Markdown  
- UTC date  

## Smoke (2026-08-05)

- snapshots_total: 2  
- accounts_covered: 1  
- RUNTIME_UNKNOWN: 2  
- high_critical_count: 2 → `REVIEW_REQUIRED` (human review; no auto send mutation)
