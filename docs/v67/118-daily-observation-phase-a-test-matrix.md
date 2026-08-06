# V67.1 — Daily Observation Phase A Test Matrix

## Suites

- `tests/test_v67_daily_observation_contract.py`
- `tests/test_v67_daily_observation_validator.py`
- `tests/test_v67_daily_observation_ticks.py`
- `tests/test_v67_daily_observation_infra.py`
- `tests/test_v67_daily_observation_cli.py`
- `tests/test_v67_daily_observation_isolation.py`
- `tests/test_v67_daily_observation_readonly_proof.py`
- `tests/test_v67_phase7_daily_report.py` (updated wrapper)

## Coverage themes

Contract version/serialization/hard false flags; Session bounds; expected ticks; fail-closed validator precedence; infra degrade/unknown; CLI exit codes and formats; no frontend/API/migration; no commit/add/flush; Celery interval alignment.

## Regressions to run with Phase A

Phase 7 shadow engine/runtime, migration DB guard, daily report wrapper, send_gate untouched checks as already present in Phase 7 suites.
