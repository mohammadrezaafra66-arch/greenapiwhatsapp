# V67.1 — Daily Observation Data Contract

**Version:** `v67.owner.daily-observation.1`  
**Owner Change:** Read-Only Daily Observation Report — Phase A

## Module

`backend/app/services/daily_observation/contract.py` — `DailyObservationReport`

## Hard invariants

- `phase7_fully_accepted` always `false` in `to_dict()`
- `phase8_allowed` always `false` in `to_dict()`
- `read_only` always `true`

## Sections

Identity, overall result, snapshot, mismatch, infrastructure, safety (with runtime vs static evidence lists), validity.

## Status enums

- Overall / daily validity: `PASS` | `FAIL` | `REVIEW_REQUIRED` | `INSUFFICIENT_EVIDENCE` | `NOT_APPLICABLE`
- Infra: `HEALTHY` | `UNHEALTHY` | `DEGRADED` | `UNKNOWN` | `NOT_APPLICABLE`
- Evidence: includes `INSUFFICIENT_EVIDENCE`

## Session

Logical `session-2` only. Dates before Session 2 start → `NOT_APPLICABLE`.
