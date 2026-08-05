# V67.1 Phase 2 — Database Audit (read-only)

**Date:** 2026-08-05  
**Branch:** `feature/v67-autonomous-fleet-manager`  
**Mode:** Read-only inspection before migrations  
**No DDL applied in this audit.**

---

## 1. Runtime / containers

| Item | Value |
|---|---|
| Backend | `claudegreenapi-backend-1` |
| DB | `claudegreenapi-db-1` (postgres:15-alpine) |
| Redis | `claudegreenapi-redis-1` |
| DB name | `whatsapp_sender` |
| DB user / owner | `afrakala` |
| Schema | `public` |
| PostgreSQL | 15.18 (x86_64-pc-linux-musl) |
| Async URL | `postgresql+asyncpg://afrakala:***@db:5432/whatsapp_sender` |
| Sync URL | `postgresql://afrakala:***@db:5432/whatsapp_sender` |

---

## 2. Schema authority (current)

| Layer | Role |
|---|---|
| SQLAlchemy `Base.metadata` + `app.models` | ORM source of truth for most tables |
| `Base.metadata.create_all` on startup (`main.py` lifespan) | Creates missing tables from models |
| `main.py` `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` | Additive patches for columns/tables not fully covered by create_all (enums, late columns) |
| Alembic | **Configured** (`alembic.ini`, `migrations/env.py`) but **no revisions** and **no `alembic_version` table** on live DB |

**Conclusion:** Current operational authority is **startup create_all + main.py DDL**, not Alembic. Alembic is safe to introduce via baseline stamp.

---

## 3. Live table inventory

73 public tables observed (sample includes `accounts`, `account_incidents`, `warmup_enrollment`, `instance_live_state`, campaigns, helpers, etc.).

Notable:

- `instance_live_state` **exists** live (ORM + create_all path; previously flagged as ORM-only in Phase 0).
- No `fleet_accounts` / `fleet_policies` yet.
- No `alembic_version`.

No material conflict with documented Account / Warmup / Incident models for Phase 2 additive work.

---

## 4. Alembic status

| Check | Result |
|---|---|
| Package installed | Yes — Alembic 1.13.1 (in backend image) |
| SQLAlchemy | 2.0.30 |
| `alembic.ini` | Present; `script_location = migrations` |
| `migrations/env.py` | Imports `Base` + `app.models`; uses `SYNC_DATABASE_URL` / settings |
| `migrations/versions/` | Empty / absent before Phase 2 |
| Live stamped? | No |

---

## 5. Baseline strategy (approved D-H5)

1. Revision `v67_01_baseline_stamp` — **empty** upgrade/downgrade (no recreate of existing tables).
2. On existing/dev/prod-like DB: `alembic stamp v67_01_baseline_stamp` (or upgrade empty), then upgrade additive heads.
3. On fresh test DB: create_all (startup) OR stamp baseline after create_all; then upgrade fleet revisions.
4. Keep `main.py` IF NOT EXISTS safety net for **one compatibility release**; do **not** remove in Phase 2.
5. New fleet DDL **only** via Alembic revisions (additive); models registered so create_all also creates fleet tables on brand-new empties (idempotent with IF NOT EXISTS in migrations).

**Hard-stop checks:** PASSED

- Live schema does not contradict docs for Phase 2 scope.
- DB owner clear (`afrakala` / `whatsapp_sender`).
- Baseline can be stamped safely (noop).
- No drop/rename of existing data planned.
- Startup DDL coexists (hybrid one release).
- No table naming conflicts (`fleet_*` free).

---

## 6. Exact proposed tables (Phase 2 only)

Per `17` / `18` / execution prompt: **only** `fleet_policies` + `fleet_accounts`.

### `fleet_policies`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | varchar | e.g. CONSERVATIVE |
| version | int | monotonic per name |
| is_active | bool | |
| is_default | bool | only CONSERVATIVE default |
| policy_type | varchar | CONSERVATIVE / BALANCED / EXPERIMENTAL |
| settings_json | JSONB | ramp, thresholds placeholders |
| created_at / updated_at | timestamp | |

Constraints: unique `(name, version)`; at most one `is_default=true` (partial unique index).

### `fleet_accounts`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| account_id | UUID FK → accounts.id UNIQUE | ON DELETE CASCADE |
| fleet_state | varchar + CHECK | Canonical FleetState |
| journey_type | varchar nullable | |
| journey_profile_id | UUID nullable | |
| policy_id | UUID FK → fleet_policies.id nullable | |
| risk_budget | varchar default NORMAL | overlay axis |
| cutover | bool default false | |
| registered_at … mature_at, next_action_at | timestamp nullable | evidence anchors; no fabricated maturity |
| paused_reason / state_reason | text nullable | |
| state_changed_at | timestamp | |
| version | int | optimistic concurrency |
| created_at / updated_at | timestamp | |

Indexes: UNIQUE(account_id); (fleet_state); (cutover, fleet_state); (policy_id).

**Not in Phase 2:** journeys, actions, metrics, certificates, capacity_decisions (deferred).

---

## 7. Rollback strategy

| Revision | Downgrade |
|---|---|
| baseline stamp | no-op |
| fleet_policies | DROP TABLE IF EXISTS fleet_policies |
| fleet_accounts | DROP TABLE IF EXISTS fleet_accounts |

Never drop `accounts` / `warmup_*`. Seed is additive rows only; dry-run default; no auto production seed.

---

## 8. Production execution rules

- Do **not** apply migrations to production automatically in Phase 2 agent work.
- Dev/test DB (`claudegreenapi-db-1` / whatsapp_sender) may receive additive upgrade for local verification.
- Seed/backfill: fixtures + `--dry-run` by default; `--apply` only on explicit local/test runs.
