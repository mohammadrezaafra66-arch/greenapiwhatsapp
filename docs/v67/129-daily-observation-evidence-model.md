# V67.1 — Daily Observation Evidence Model

## Name

`DailyObservationEvidenceBundle`

## Version

`v67.owner.daily-observation.evidence.1`

## Role

Read-only structured evidence attached to the Phase A report. **Not** a parallel validator or aggregation engine.

## Fields (minimum)

- report_date / session / generated_at
- deployed_git_sha / shadow_version / policy_version / migration_revision
- runtime_items / static_items / partial_items / missing_items
- correlation_sample + correlation_status
- can_support_daily_pass (production collector always `false` until attributed ledger exists)
- false_pass_guards
- read_only=true

## Serialization

`owner_safe_dict()` — no secrets, phones, raw messages. Frontend consumes via existing GET delivery.
