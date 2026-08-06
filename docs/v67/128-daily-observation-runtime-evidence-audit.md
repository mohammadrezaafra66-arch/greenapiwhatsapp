# V67.1 — Daily Observation Runtime Evidence Audit (Phase C)

## Purpose

Classify every available source that could support (or honestly refuse) daily Observation validity. Principle: **NO FALSE PASS**.

## Classes

- `RUNTIME_VERIFIED` — day-scoped, queryable, timestamped, reliable enough for that invariant
- `STATIC_VERIFIED` — release/architecture proof; never alone unlocks daily PASS
- `PARTIALLY_OBSERVED` — bounded probe without Shadow attribution
- `NOT_OBSERVABLE` — no honest query path without unbounded scan or new ledger/migration

## Inventory (summary)

### RUNTIME_VERIFIED

| Invariant | Source | Notes |
| --- | --- | --- |
| Snapshot flags | `fleet_shadow_snapshots` day window | simulation_only / mutates_runtime / executes |
| Periodic coverage | same, `source=CELERY_PERIODIC` | counts + cohort |
| Cutover count | `fleet_accounts.cutover` | point-in-time (not EOD ledger) |
| Correlation sample | snapshot columns run_id/source/versions | bounded LIMIT |
| Infra probes (current day) | DB/Redis/Celery ping | historical days use day-scoped scheduler derivation |

### STATIC_VERIFIED

| Invariant | Source |
| --- | --- |
| Shadow never calls Green API | isolation / forbidden-call tests |
| Snapshot CHECK constraints | schema |
| send_gate untouched by Shadow path | Phase 7 tests |
| Deployed SHA / contract versions | `ObservationStaticProofManifest` |

### PARTIALLY_OBSERVED

| Probe | Source | Limit |
| --- | --- | --- |
| FleetAccount updates | `fleet_accounts.updated_at` day window | unattributed |
| Journey updates | `account_journeys` / `journey_actions` | unattributed |
| Campaign sends | `campaign_contacts.sent_at` | proves activity, not Shadow cause |
| Daily send logs | `daily_send_logs.sent_at` | same |

### NOT_OBSERVABLE (blocks attributed PASS)

- Shadow-attributed send / Green API absolute absence
- Shadow-attributed campaign / journey / FleetState mutation absence
- Feature-flag history
- Process-local `shadow_metrics` as day history
- Unbounded application log scan (forbidden)
- Redis lock historical day ledger

## False-pass guards

1. Static-only evidence cannot PASS.
2. Absence of error ≠ absence of mutation.
3. Unattributed `updated_at` is never `RUNTIME_VERIFIED` for mutation attribution.
4. Unknown critical evidence keeps day at `INSUFFICIENT_EVIDENCE` / `REVIEW_REQUIRED` / `FAIL`.

## Migration decision

**NO NEW MIGRATION.** Gaps remain `NOT_OBSERVABLE` rather than inventing PASS.
