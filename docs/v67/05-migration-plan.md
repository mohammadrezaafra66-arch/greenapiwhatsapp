# V67.1 Phase 0 — Migration Plan (Proposal Only)

**No migrations were applied in Phase 0.** This document proposes how Phase 2+ should evolve schema and cut over runtime without deleting healthy services.

## 1. Current schema reality

- ORM models under `backend/app/models/`
- Startup: `Base.metadata.create_all` + large idempotent SQL in `backend/app/main.py`
- `backend/migrations/env.py` exists but is not the operational revision history
- Live DBs already contain columns added via `IF NOT EXISTS` (e.g. `connected_at`, `suspended_until`, helper delivery columns)
- `InstanceLiveState` (`instance_live_state`) is ORM-only today (no `CREATE TABLE` in `main.py`); baseline stamp must include it explicitly

## 2. Migration tooling target (Phase 2 prerequisite)

1. Introduce Alembic (or confirm team standard) with **upgrade + downgrade** for every revision  
2. Baseline revision: autogenerate empty / stamp reflecting current production schema (inventory from models + main.py DDL)  
3. Freeze new `main.py` DDL growth; new changes go through revisions only  
4. Keep startup `IF NOT EXISTS` temporarily as safety net until stamp verified on staging + prod clone  

**Hard Stop H5** in conflict map must be cleared before large fleet DDL.

## 3. Proposed new tables (additive)

All additive; FK to `accounts.id` or `accounts.instance_id` as appropriate.

| Table | Purpose | Key constraints |
|---|---|---|
| `fleet_accounts` | Projection: fleet_state, policy_id, journey_id, risk_budget, scores JSON, certificate_id | UNIQUE(account_id) |
| `fleet_policies` | Versioned CONSERVATIVE/BALANCED/EXPERIMENTAL | (name, version) unique |
| `fleet_journeys` | Journey type + state + started_at + policy_snapshot | |
| `fleet_actions` | Planned/executed actions | UNIQUE(account_id, journey_id, action_type, scheduled_slot) idempotency |
| `fleet_metrics_daily` | total_daily_flow, unique chats, bidirectional, ratios | UNIQUE(account_id, day) |
| `fleet_decisions` | Explainer audit (inputs, rule version, output) | |
| `human_participants` | Extends or parallels helpers with consent/native/reliability | phone + consent_at |
| `device_registry` | device hashes, active account, batch/cohort | |
| `maturity_certificates` | Checklist evidence + issued_at | |
| `capacity_decisions` | Per-day capacity allocation | |
| `fleet_events` | Durable webhook/domain events (complement Redis dedup) | UNIQUE(dedup_key) |

**Prefer extend-in-place when safe:**

- Add columns to `warmup_helper` for consent / native_contact_verified rather than immediate table split  
- Add `fleet_state` column on `accounts` **or** keep only on `fleet_accounts` (prefer separate table to avoid enum fights with `AccountStatus`)

## 4. Mapping migration (data backfill — read-only plan)

| Source | Target backfill |
|---|---|
| `Account.status` + live state + enrollment.state | Initial `fleet_accounts.fleet_state` via adapter matrix |
| `WarmupEnrollment` | `fleet_journeys` row type=mesh_legacy |
| `AccountOnboarding` | journeys type=onboarding |
| `account_incidents` | Risk inputs; open suspended → SUSPENDED |
| `connected_at` / `authorized_at` | Classifier evidence |
| `sent_today`/`received_today` | Seed metrics (unique chats = 0 until computed) |
| Helpers | `human_participants` copy |

Backfills must be **idempotent** and reversible (down = delete fleet_* rows only, never destroy warmup_*).

## 5. Runtime cutover stages (from master §20)

```
Audit (Phase 0 ✓)
→ Map (this doc + 01/04)
→ Adapter (Phases 1–3)
→ Shadow (Phase 12 start)
→ Compare
→ per-account Cutover
→ Deprecate
→ Remove only after rollback-tested release
```

### Stage rules

- **Shadow:** AFM writes `fleet_*` + decisions; sends still via existing runners  
- **Canary:** 1 then 2 accounts; owner approval required  
- **Rollback:** feature flag `AFM_MODE=off|shadow|canary|on`; disabling AFM leaves mesh/TC/campaign untouched  
- **Never** `git reset --hard` / force-push as part of migration ops (master Git rules)

## 6. Suggested Phase 2 revision sequence (names only)

1. `v67_01_baseline_stamp`  
2. `v67_02_fleet_policies`  
3. `v67_03_fleet_accounts_journeys`  
4. `v67_04_fleet_actions_idempotency`  
5. `v67_05_fleet_metrics_decisions`  
6. `v67_06_human_device_certificate`  
7. `v67_07_helper_consent_columns` (additive on existing helpers)  
8. `v67_08_fleet_events`

Each must include downgrade dropping only new objects.

## 7. Index / performance notes

- Index `fleet_actions(next_run_at, status)` for planner tick  
- Index `fleet_events(account_id, created_at)`  
- Index `fleet_metrics_daily(day)`  
- Keep existing campaign and enrollment indexes

## 8. Secrets / PII

- No `api_token` in fleet tables (reference `accounts` only)  
- Mask tokens in decision payloads  
- Consent evidence retention policy TBD (Phase 7+)

## 9. Test gates before applying any migration

- Empty upgrade/downgrade on disposable DB  
- Upgrade on copy of staging schema  
- App boot without duplicate-column errors  
- Existing V65/V60/V41 tests green  
- No webhook or Celery config changes in Phase 2 DDL-only PR

## 10. Explicit non-goals for early migrations

- Do not drop `warmup_enrollment` / mesh edges  
- Do not alter Green API webhook URLs  
- Do not change `AccountStatus` enum values in the same revision as fleet_state introduction  
- Do not migrate production data in Phase 1

## 11. Open questions for owner (block Phase 2 apply)

1. Alembic vs continue hybrid DDL?  
2. `fleet_state` separate table vs column on `accounts`?  
3. Helpers evolve in place vs new `human_participants`?  
4. Retention period for `fleet_events` / decisions?

---

**Phase 0 stop.** Wait for explicit `Phase 1` before any code, DDL application, or Green API changes.
