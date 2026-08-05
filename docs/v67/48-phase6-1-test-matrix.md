# V67.1 Phase 6.1 — Test Matrix

## Remediation coverage

| Area | Status |
|---|---|
| Missing / empty policy → NOT_ELIGIBLE | PASS |
| Missing eligibility_rules → NOT_ELIGIBLE (no silent fallback) | PASS |
| Invalid eligibility_rules → NOT_ELIGIBLE | PASS |
| Policy version missing → NOT_ELIGIBLE | PASS |
| Schema validator + monotonicity | PASS |
| READY_FOR_TRIAL cannot unlock Limited | PASS |
| High volume requires READY_FOR_MATURE | PASS |
| Journey PAUSED/FAILED/CANCELLED/SIMULATING/missing/unknown | PASS |
| Unknown risk/readiness/fleet_state | PASS |
| Tier gap explainability | PASS |
| CLI dry-run (no `or True`) | PASS |
| API 404 + dry-run default | PASS |
| Cutover persist refusal | PASS |
| send_gate / Celery / Green API isolation | PASS |
| No new DDL | PASS |

## Baseline

- Before Phase 6.1: **1769 passed, 0 failed**
- After Phase 6.1: **1777 passed, 0 failed** (+8)
- V67 Phase 1–6 regressions: **116 passed**
