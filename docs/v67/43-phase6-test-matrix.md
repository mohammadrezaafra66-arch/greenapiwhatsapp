# V67.1 Phase 6 — Test Matrix

| Area | Coverage | File |
|---|---|---|
| Deterministic same inputs | same decision | `test_v67_phase6_eligibility.py` |
| Breaker / major incidents | NOT_ELIGIBLE | same |
| Blocked FleetState | NOT_ELIGIBLE | same |
| Journey FAILED | NOT_ELIGIBLE | same |
| Trust / risk / capacity / budget | blocks tier | same |
| Limited / standard / high volume | tier ladder | same |
| Policy threshold change | decision flips | same |
| Missing incident_free_days | NOT_ELIGIBLE | same |
| Explanation fields | present | same |
| API routes | registered | same |
| CLI module | entrypoint | same |
| send_gate isolation | no leak | same |
| Engine purity | no IO / Celery / Green API | same |
| Migration | reuses `fleet_plan_snapshots` (v67_06); no new DDL | `test_v67_phase6_migrations.py` |

## Results (2026-08-05)

| Suite | Result |
|---|---|
| Phase 6 unit + migration | **16 passed** |
| Phase 1–6 V67 regressions | **108 passed** |
| Full Backend | **1769 passed, 0 failed** |

Baseline before Phase 6: **1753 passed, 0 failed** (+16 Phase 6 tests).
