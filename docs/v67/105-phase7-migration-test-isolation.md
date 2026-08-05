# V67.1 Phase 7 Completion — Migration Test Isolation (STEP 1)

## Reason

Session 1 observation became invalid when Alembic upgrade/downgrade tests ran inside `claudegreenapi-backend-1` against live `SYNC_DATABASE_URL` → `whatsapp_sender` (ENV-A). Downgrade dropped and recreated empty `fleet_*` tables.

## Implementation

| Piece | Role |
|---|---|
| `app/services/migration_db_guard.py` | Detect protected DB name `whatsapp_sender`; refuse migration-test targets; refuse Alembic downgrade unless `V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE=1` |
| `migrations/env.py` | Hard-stop on `downgrade` against ENV-A |
| `tests/migration_test_db.py` | Disposable DB `whatsapp_sender_migtest`; forces `SYNC_DATABASE_URL` for Alembic subprocess |
| Phase 2–5 + Phase 7 roundtrip tests | Use migtest helpers only |
| `tests/test_v67_migration_db_guard.py` | Guard + CLI refuse proofs |

## Tests

12 passed (guard + phase2–5 + phase7 roundtrip). After suite: ENV-A `fleet_accounts=0`, `fleet_shadow_snapshots=0` unchanged (still empty from Session 1 wipe; not further damaged).

## Risks

- Emergency ENV-A downgrade requires explicit env override (intentional).
- Migtest DB shares Postgres instance but not data with ENV-A.

## Rollback

Revert guard/env/test changes; do **not** re-point tests at `whatsapp_sender`.

## Remaining

Recover V67 metadata; re-enroll Stage A; start Observation Session 2 Day 0; complete 14 real days.
