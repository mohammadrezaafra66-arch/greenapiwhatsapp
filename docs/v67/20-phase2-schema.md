# V67.1 Phase 2 — Schema

**Branch:** `feature/v67-autonomous-fleet-manager`  
**Applied:** additive Alembic revisions only (dev/test verified)

## Tables

### `fleet_policies`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | varchar(80) | CONSERVATIVE |
| version | int | unique with name |
| is_active | bool | |
| is_default | bool | partial unique where true |
| policy_type | varchar(40) | CONSERVATIVE default; no EXPERIMENTAL default |
| settings_json | jsonb | ramp + placeholders |
| created_at / updated_at | timestamp | |

### `fleet_accounts`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| account_id | UUID UNIQUE FK → accounts.id ON DELETE CASCADE | one-to-one |
| fleet_state | varchar CHECK | canonical AFM truth |
| journey_type | varchar nullable | storage only |
| journey_profile_id | UUID nullable | |
| policy_id | UUID FK → fleet_policies ON DELETE SET NULL | |
| risk_budget | varchar default NORMAL | overlay axis |
| cutover | bool default false | |
| registered_at … mature_at, next_action_at | timestamp nullable | no fabricated maturity |
| paused_reason / state_reason | text | |
| state_changed_at | timestamp | |
| version | int | optimistic concurrency |
| created_at / updated_at | timestamp | |

## Indexes / constraints

- `uq_fleet_policies_name_version`
- `uq_fleet_policies_one_default` (partial)
- `uq_fleet_accounts_account_id`
- `ck_fleet_accounts_fleet_state`
- `ix_fleet_accounts_fleet_state`
- `ix_fleet_accounts_cutover_state`
- `ix_fleet_accounts_policy_id`
- `ix_fleet_accounts_next_action_at`

## Not created in Phase 2

journeys, actions, metrics, certificates, capacity_decisions (deferred per `17`/`18`).

## Compatibility

`main.py` create_all + IF NOT EXISTS retained one release (D-H5). Fleet migrations use `IF NOT EXISTS` for hybrid safety.
