# V67.1 Phase 6 — Campaign Eligibility Engine

**Module:** `app.services.campaign_eligibility.CampaignEligibilityEngine`  
**Facade:** `app.services.eligibility_service.EligibilityService`  
**Validator:** `app.services.eligibility_policy.validate_eligibility_rules`  
**Decision version:** `v67.6.eligibility.2` (bumped in Phase 6.1)  
**Mode:** simulation / decision only — never executes

## Fail-closed policy contract

- Missing policy → `NOT_ELIGIBLE` (`policy_missing`)
- Empty settings → `NOT_ELIGIBLE`
- Missing `eligibility_rules` → `NOT_ELIGIBLE` (`eligibility_rules_missing`)
- Invalid rules → `NOT_ELIGIBLE` (`eligibility_rules_invalid:*`)
- Missing `policy_version` → `NOT_ELIGIBLE` (`policy_version_missing`)
- **No silent Conservative fallback inside the pure engine**
- Service may select Conservative **explicitly** when DB has no default policy (`policy_source=explicit_conservative_default`)
- DB policy lacking rules is **not** silently patched

## Outputs

`NOT_ELIGIBLE` | `ELIGIBLE_FOR_TRIAL` | `ELIGIBLE_FOR_LIMITED_CAMPAIGN` | `ELIGIBLE_FOR_STANDARD_CAMPAIGN` | `ELIGIBLE_FOR_HIGH_VOLUME`

Every decision includes reason_codes, blocking/required evidence, next_recommendation, policy_version, decision_version, optional `policy_source`, `closest_tier`, `tier_gaps`.

## Forbidden

No send_gate / Celery / Green API / FleetState / Journey mutation / live campaign / Autopilot / Cutover / Shadow / Canary.
