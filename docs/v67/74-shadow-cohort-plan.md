# V67.1 Phase 7.2 — Shadow Cohort Plan

**Do not enroll accounts in Phase 7.2.**

## Prerequisite blocker (ENV-A)

`fleet_accounts=0`. ShadowRuntimeService requires a FleetAccount (`fleet_account_missing` otherwise).  
Cohort selection cannot proceed until Fleet enrollment/seed exists and owner approves criteria.

## Stages (future)

### Stage A — Manual proof (1–3 accounts)

- Criteria: `cutover=false`; preferably no open severe incidents; diverse statuses if available
- Actions: dry-run only first; optional explicit persist only after D-SE-05
- Scheduler: **off**

### Stage B — Small controlled set (3–10)

- Verify locks, idempotency, monitoring cadence
- Scheduler still owner-gated (D-SE-07)

### Stage C — Approved observation cohort

- Only after Stage A/B acceptance
- 14-day window only via separate command (D-SE-09)

## Selection criteria (no live IDs listed)

- FleetState diversity when available
- Journey status known
- Trust/Risk range coverage
- Activity without active major incident where possible
- No `cutover=true`
- Operator ownership clear
- Mask identifiers in reports (no unnecessary phone/PII)

## Current ENV-A account shape (aggregated only)

| status | count |
|---|---|
| active | 21 |
| other (deleted/suspended/pending/disconnected/green_api_deleted) | 5 |

## Owner decision

D-SE-04 must approve Stage A count/criteria after FleetAccount rows exist.
