# V67.1 Phase 6 — Decision Matrix

## Hard blocks (policy `eligibility_rules`)

| Condition | Result |
|---|---|
| Policy missing / empty / invalid | NOT_ELIGIBLE |
| eligibility_rules missing / empty / invalid | NOT_ELIGIBLE |
| policy_version missing | NOT_ELIGIBLE |
| Breaker tripped | NOT_ELIGIBLE |
| Open major incident | NOT_ELIGIBLE |
| FleetState in blocked set / unknown | NOT_ELIGIBLE |
| incident_free_days missing / below policy | NOT_ELIGIBLE |
| Journey PAUSED / FAILED / CANCELLED | NOT_ELIGIBLE |
| Journey SIMULATING | NOT_ELIGIBLE (not operational) |
| Journey missing / unknown / not allowed | NOT_ELIGIBLE |
| Unknown risk / readiness | NOT_ELIGIBLE |

## Tier readiness (monotonic)

| Decision | Min readiness |
|---|---|
| ELIGIBLE_FOR_TRIAL | READY_FOR_TRIAL (or higher) |
| ELIGIBLE_FOR_LIMITED_CAMPAIGN | READY_FOR_CAMPAIGN+ (**not** Trial-only) |
| ELIGIBLE_FOR_STANDARD_CAMPAIGN | READY_FOR_CAMPAIGN+ |
| ELIGIBLE_FOR_HIGH_VOLUME | READY_FOR_MATURE only (fail-closed until owner unlocks) |

## Journey matrix

| Status | Effect |
|---|---|
| ACTIVE | Allowed for eligibility |
| PAUSED / FAILED / CANCELLED | Hard block |
| SIMULATING | Block — simulation diagnostics only |
| COMPLETED / missing / unknown | Fail closed (owner D-P7-13/14) |

Threshold numbers live only in policy JSON.
