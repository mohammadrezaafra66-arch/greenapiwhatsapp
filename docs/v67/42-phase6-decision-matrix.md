# V67.1 Phase 6 — Decision Matrix

## Hard blocks (policy `eligibility_rules`)

| Condition | Result | Typical reason_codes |
|---|---|---|
| `block_on_breaker` + breaker tripped | NOT_ELIGIBLE | `breaker_blocks_eligibility` |
| Open major incident (`major_incident_types`) | NOT_ELIGIBLE | `major_incidents:...` |
| FleetState in `blocked_fleet_states` | NOT_ELIGIBLE | `fleet_state_blocked:...` |
| `incident_free_days` missing / below `min_incident_free_days` | NOT_ELIGIBLE | `incident_free_days_*` |
| Journey status FAILED / CANCELLED | NOT_ELIGIBLE | `journey_status:...` |
| Invalid / missing policy rules | NOT_ELIGIBLE | `policy_invalid` / `eligibility_rules_missing` |

## Tier selection (highest first)

Engine evaluates tiers top-down; first full match wins.

| Decision | Fleet states (policy) | Trust / Risk / Readiness / Capacity / Budget |
|---|---|---|
| ELIGIBLE_FOR_HIGH_VOLUME | `high_volume_fleet_states` | `high_volume_*` + `require_readiness_for_high_volume` |
| ELIGIBLE_FOR_STANDARD_CAMPAIGN | `standard_fleet_states` | `standard_*` |
| ELIGIBLE_FOR_LIMITED_CAMPAIGN | `limited_fleet_states` | `limited_*` |
| ELIGIBLE_FOR_TRIAL | `trial_fleet_states` | `trial_*` |
| NOT_ELIGIBLE | no tier matched | `no_eligibility_tier_matched` |

Conservative seed defaults (illustrative — source of truth is policy JSON):

| Tier | States | Min trust | Max risk | Min capacity | Min usage |
|---|---|---|---|---|---|
| Trial | WARMUP_READY, GRADUATION_TRIAL | 55 | LOW | 1 | 1 |
| Limited | GRADUATION_TRIAL, CAMPAIGN_READY | 65 | LOW | 5 | 3 |
| Standard | CAMPAIGN_READY, MATURE, MAINTENANCE | 75 | NORMAL | 20 | 10 |
| High volume | MATURE, MAINTENANCE | 85 | NORMAL | 50 | 30 |

## Risk ordering (must match RiskEngine)

`NORMAL < LOW < MEDIUM < HIGH < CRITICAL` (NORMAL = healthiest).

## Next recommendations (eligible)

| Decision | next_recommendation |
|---|---|
| HIGH_VOLUME | `simulate_high_volume_plan_only` |
| STANDARD | `simulate_standard_campaign_plan_only` |
| LIMITED | `simulate_limited_campaign_plan_only` |
| TRIAL | `simulate_graduation_trial_only` |
| NOT_ELIGIBLE (blocks) | `resolve_blocks_then_reevaluate` |
| NOT_ELIGIBLE (tier miss) | `improve_trust_risk_readiness_capacity_or_state` |
