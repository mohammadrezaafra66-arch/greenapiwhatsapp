# V67.1 Phase 7.3 — Backup and Rollback Proof

## Backup

| Field | Value |
|---|---|
| Timestamp (UTC) | 2026-08-05T17:10:06Z |
| Path | `backups/envA_whatsapp_sender_20260805_204002.dump` (gitignored) |
| Format | `pg_dump -Fc` |
| Size | 49,156,681 bytes |
| SHA256 | `3AF2FB538D090F5ECFCE58C27177C55AFE39DD19A323EC652B1737616D22E3A6` |
| Database | `whatsapp_sender` |
| Alembic at backup | `v67_07_fleet_shadow_snapshots` |

Credentials not recorded.

## Restore verification

Created disposable DB `whatsapp_sender_restore_check`, restored dump, verified:

- `accounts=26`
- `alembic=v67_07_fleet_shadow_snapshots`
- `shadow=0`

Dropped disposable DB. **Did not restore over ENV-A.**

## Rollback (Shadow)

1. Set both Shadow flags false; recreate Backend/workers/Beat  
2. Optional: `alembic downgrade v67_06_fleet_plan_snapshots` (drops Shadow table only)
