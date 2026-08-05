# V67.1 Phase 7.2 — Shadow Migration Preflight

## ENV-A (candidate) — read-only inspection

| Check | Result |
|---|---|
| Current Alembic revision | `v67_07_fleet_shadow_snapshots` |
| Alembic heads | Single head: `v67_07_fleet_shadow_snapshots` |
| Table `fleet_shadow_snapshots` | Exists |
| Indexes | Present including HIGH/CRITICAL partial index |
| Shadow rows | `0` |
| Defaults | `simulation_only=true`, `mutates_runtime=false`, `executes=false`, threshold `UNRATIFIED` |
| Fleet tables remain | Yes (Phase 2–6 objects present; `fleet_accounts` count 0) |

## Future apply command (NOT executed in Phase 7.2)

If another environment lacks the revision:

```bash
docker exec -w /app <backend-container> alembic upgrade head
```

## Rollback command (NOT executed)

```bash
docker exec -w /app <backend-container> alembic downgrade v67_06_fleet_plan_snapshots
```

Drops only `fleet_shadow_snapshots` (+ its indexes).

## Backup procedure (owner ops)

Before any future migration on a named env:

1. `pg_dump` of `whatsapp_sender` (or volume snapshot)
2. Record `alembic_version`
3. Confirm free disk (ENV-A DB volume showed large free space in `df`)

## Transaction / lock impact

Alembic reports transactional DDL on Postgres. `v67_07` is additive CREATE TABLE/INDEX — already applied on ENV-A.

## ENV-B / disposable

Allowed for upgrade/downgrade/re-upgrade rehearsals on disposable DB only. Phase 7.2 did not create a new disposable DB; migration correctness already covered by Phase 7/7.1 tests (container roundtrip where available).

## Migration readiness for ENV-A

**Technically applied: YES.**  
**Authorized to rely on for observation: pending D-SE-02 owner confirmation.**
