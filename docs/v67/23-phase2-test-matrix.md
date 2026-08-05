# V67.1 Phase 2 — Test Matrix

## Unit (`test_v67_phase2_fleet_state.py`)

| Case | Result |
|---|---|
| Enum completeness (22 states) | PASS |
| Day-10 MATURING → WARMUP_READY | PASS |
| GRADUATED → WARMUP_READY never CAMPAIGN_READY | PASS |
| No auto CAMPAIGN_READY / MATURE | PASS |
| Suspended / blocked / forced_logout precedence | PASS |
| Incident over warmup | PASS |
| Ambiguous conservative | PASS |
| Policy ramp 12→100 + flow metric | PASS |
| Mapping idempotent | PASS |

## Seed / gate (`test_v67_phase2_seed_and_gate.py`)

| Case | Result |
|---|---|
| send_gate has no FleetState cutover | PASS |
| Seed forbidden states | PASS |
| Mesh autochat class default OFF | PASS |

## Migration (`test_v67_phase2_migrations.py`)

| Case | Result |
|---|---|
| Alembic heads/history | PASS |
| Upgrade / downgrade / re-upgrade + constraints | PASS |

## Regression

| Suite | Result |
|---|---|
| Phase 1 safety | PASS |
| Phase 1.1 Bugbot | PASS |

## Full Backend suite (once, 2026-08-05)

| Metric | Value |
|---|---|
| Passed | **1712** |
| Failed | **0** |
| Prior Phase 1.1 baseline | 1696 |
| Assertions weakened | **no** |
