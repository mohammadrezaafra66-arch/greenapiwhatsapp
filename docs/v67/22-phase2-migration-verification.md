# V67.1 Phase 2 — Migration Verification

## Revisions

| Rev | Purpose |
|---|---|
| `v67_01_baseline_stamp` | Empty baseline (stamp existing schema) |
| `v67_02_fleet_policies` | Additive `fleet_policies` (IF NOT EXISTS) |
| `v67_03_fleet_accounts` | Additive `fleet_accounts` (IF NOT EXISTS) |

## Verified on `claudegreenapi-db-1` / `whatsapp_sender` (2026-08-05)

1. Stamp baseline → OK  
2. Upgrade head → `fleet_policies` + `fleet_accounts` present; `alembic_version=v67_03_fleet_accounts`  
3. Downgrade to baseline → fleet tables dropped  
4. Re-upgrade head → tables restored  

## Rollback

Downgrade drops only fleet_* objects. Never touches `accounts` / `warmup_*`.

## Production

Do not auto-apply to production. Owner must approve production migrate separately.
