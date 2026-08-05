# V67.1 Phase 1 — Test Matrix

## Targeted unit (`tests/test_v67_phase1_safety.py` + `test_campaign_lock.py`)

| Case | Result |
|---|---|
| suspended / blocked / notAuthorized eligibility | PASS |
| unknown live state exclusion | PASS |
| unresolved critical exclusion | PASS |
| fleet breaker exclusion | PASS |
| healthy authorized allow | PASS |
| real outbound definitions (idMessage / delivery_ok) | PASS |
| failed/missing id excluded | PASS |
| Redis unavailable → lock fail-closed | PASS |
| lock held skip | PASS |
| wrong owner release | PASS |
| fleet breaker blocks campaign | PASS |
| two distinct suspensions trip logic | PASS |
| breaker Redis fail-closed | PASS |
| blocked incident idempotent | PASS |
| forced_logout create | PASS |
| mesh autochat default OFF | PASS |
| mesh skip when disabled | PASS |
| mesh blocked by fleet breaker when enabled | PASS |
| campaign lock acquire/release | PASS |

## Integration-style (mocked)

| Case | Coverage |
|---|---|
| webhook blocked → incident | `record_blocked` + webhook wiring |
| webhook notAuthorized → forced_logout | webhook handler |
| suspension → fleet breaker notify | `record_suspension` |
| campaign entry fleet breaker | `run_campaign` |
| mesh/TC gate | `execute_action` / `_send_from_main` |

## Regression (selected)

| Suite | Result |
|---|---|
| `test_v65_webhook_dedup_and_suspension` | PASS (prior run) |
| `test_v27_part1` (updated for mesh flag) | PASS |
| `test_v60_step0_parallel_brakes` (CampaignLock assert) | PASS |
| `test_campaign_lock` | PASS |

## Full Backend suite (once, 2026-08-05)

| Metric | Value |
|---|---|
| Passed | **1684** |
| Failed | **0** |
| Baseline failures | **none** |
| Assertions weakened | **no** |

Command: `docker exec claudegreenapi-backend-1 pytest tests/ -q --tb=no`
