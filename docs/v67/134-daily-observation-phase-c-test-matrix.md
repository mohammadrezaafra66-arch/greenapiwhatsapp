# V67.1 — Phase C Test Matrix

Covered by:

- `tests/test_v67_daily_observation_phase_c.py`
- existing Phase A/B validator/delivery/isolation/readonly suites
- frontend `ownerViewModel.test.js`

## Highlights

1. Evidence version constants
2. Static-only cannot PASS
3. Manifest MISMATCH → FAIL
4. False-pass guard when bundle claims support with insufficient mutation
5. Collector marks NOT_OBSERVABLE + can_support_daily_pass=false
6. Collector source has no INSERT/UPDATE/DELETE/commit
7. Beat schedule registers daily task
8. Task source has no Green API / campaign send
9. Path traversal rejected for report files
10. Previous completed UTC day helper
11. UI maps evidence/stop conditions without recomputing validity

Full Backend / Frontend suites executed in Phase C final report.
