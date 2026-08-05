# V67.1 Phase 6 — Campaign Eligibility Engine

**Module:** `app.services.campaign_eligibility.CampaignEligibilityEngine`  
**Facade:** `app.services.eligibility_service.EligibilityService`  
**Decision version:** `v67.6.eligibility.1`  
**Mode:** simulation / decision only — never executes

## Goal

Decide campaign eligibility from sensors. Engine decides. Engine never executes.

## Inputs

| Input | Source |
|---|---|
| FleetState | `fleet_accounts.fleet_state` (+ inject override) |
| Journey | active/paused/simulating `account_journeys.status` |
| Trust | Phase 4 TrustEngine via FleetScoringService |
| Risk | Phase 4 RiskEngine |
| Readiness | Phase 4 ReadinessEvaluator |
| Capacity | Phase 5 CapacityPlanner |
| Budget | Phase 5 FleetBudgetEngine |
| Policy | default `fleet_policies` + `eligibility_rules` |
| Incidents | evidence / inject |
| Breaker | inject or `fleet_breaker.is_tripped` (read-only) |
| Evidence | scoring evidence snapshot fields |

## Outputs

- `NOT_ELIGIBLE`
- `ELIGIBLE_FOR_TRIAL`
- `ELIGIBLE_FOR_LIMITED_CAMPAIGN`
- `ELIGIBLE_FOR_STANDARD_CAMPAIGN`
- `ELIGIBLE_FOR_HIGH_VOLUME`

Every decision includes:

- `reason_codes`
- `blocking_evidence`
- `required_evidence`
- `next_recommendation`
- `policy_version`
- `decision_version`
- `simulation_only=true`
- `mutates_runtime=false`
- `executes=false`

## Policy

Thresholds live in `CONSERVATIVE_POLICY_SETTINGS["eligibility_rules"]`  
(and DB `FleetPolicy.settings_json`). Engine body contains no numeric thresholds.

## Persistence

Optional dry-run persist to `fleet_plan_snapshots` with `plan_type="eligibility"`.  
Refuses persist when `fleet.cutover=true`. Reuses Phase 5 table — no new DDL.

## Forbidden (enforced by design)

- No `send_gate` calls or mutations
- No Celery dispatch
- No Green API
- No FleetState / Journey / Trust / Risk / Capacity mutation
- No live campaign execution
- No Autopilot / Cutover / Shadow / Canary

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/fleet/eligibility` | fleet list decisions |
| GET | `/api/v1/fleet/eligibility-preview` | single account |
| POST | `/api/v1/fleet/simulate-eligibility` | dry-run default; injects allowed |

## CLI

```bash
python -m app.scripts.eligibility_simulate --account-id <uuid>
```
