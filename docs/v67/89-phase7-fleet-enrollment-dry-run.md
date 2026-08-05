# V67.1 Phase 7.3 — Fleet Enrollment Dry-Run

Command (twice):

`python -m app.scripts.fleet_seed --account-id <selected> --dry-run`

## Results (identical both runs)

| Field | Value |
|---|---|
| dry_run | true |
| count | 1 |
| action | create |
| to_state | `INBOUND_BUILDING` |
| reason | `activity_inbound_only` |
| CAMPAIGN_READY | no |
| MATURE | no |
| cutover | not set (defaults false) |

No DB write on dry-run (ROLLBACK observed).
