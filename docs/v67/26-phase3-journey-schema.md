# V67.1 Phase 3 — Journey Schema

## Tables

### `account_journeys`
One simulation/shadow journey per active fleet account (partial unique on ACTIVE/PAUSED/SIMULATING).

Fields: id, account_id, fleet_account_id, journey_type, profile_policy_id, status, current_state, timestamps, failure_reason, policy_snapshot JSONB, evidence_snapshot JSONB, simulation_only=true, shadow_mode=true, version.

### `journey_actions`
Planned simulation actions only (`simulation_only=true`, status PLANNED).

Unique `idempotency_key` = `account_id:journey_id:action_type:scheduled_slot`.

Allowed action types: WAIT, VERIFY_STATE, VERIFY_SETTINGS, REQUEST_INBOUND, PREPARE_REPLY, CHECK_EVIDENCE, CHECK_QUEUE, CHECK_WEBHOOK, REEVALUATE, PAUSE, REQUIRE_OWNER_REVIEW.

Forbidden: SEND_*, CAMPAIGN_SEND, etc.

## Migration

`v67_04_account_journeys` — additive, IF NOT EXISTS, downgrade drops journey tables only.
