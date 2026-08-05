# V67.1 Phase 2 — Blocker Closure

**Date:** 2026-08-05  
**Branch:** `feature/v67-autonomous-fleet-manager`  
**Mode:** Documentation / readiness only  
**Prohibitions honored:** No Alembic apply, no `fleet_accounts` DDL, no FleetState/Policy/Journey code, no Green API, no account mutation, no commits in this pass until owner accepts the closure report.

Sources read completely:

- `docs/v67/14-phase2-readiness.md`
- `docs/v67/16-phase2-readiness-after-bugfix.md`
- `docs/v67/09-owner-decisions.md`
- `docs/v67/10-phase1-readiness.md`
- `docs/v67/15-phase1-1-bugbot-remediation.md`

Supporting freeze authority (already committed Phase 0/0.5): `05-migration-plan.md`, `06-architecture-reconciliation.md`, `07-fleet-state-matrix.md`.

---

## 1. Extracted blockers (exact inventory)

| # | Exact blocker text | Primary source | Also listed in |
|---|---|---|---|
| B1 | Explicit owner command — `Execute V67.1 Phase 2` | `14` § Unresolved Phase 2 blockers #1; Verdict | `16` § Blockers #1; `10` § Recommended next; `15` § Phase 2 |
| B2 | DDL design freeze — `fleet_accounts` columns + indexes; optional activity cache columns (not applied in Phase 1) | `14` § Unresolved #2 | `16` § Blockers #2; `14` § Proposed Phase 2 DDL |
| B3 | Alembic introduction on a codebase that currently uses startup DDL (`main.py`) — migration plan in `05` / `06` | `14` § Unresolved #3 | `16` § Blockers #3; `05` §2; `06` B5 / H5 |
| B4 | Day-ladder migration (D-H2) — Phase 1 did not change Day-10 semantics; Phase 2+ must map mesh GRADUATED carefully | `14` § Unresolved #4 | `16` § Blockers #4; `09` D-H2 |
| B5 | Mesh cutover — WRAP only; deprecate only after canary (D-H1) | `14` § Unresolved #5 | `16` § Blockers #5; `09` D-H1 |
| B6 | Live-state policy — `automated_require_live_state=False` default; Phase 2 may tighten after FleetState hydration is reliable | `14` § Unresolved #6 | (not in `16` list; retained from `14`) |

### Non-blockers confirmed closed (context only)

| Item | Source | Status |
|---|---|---|
| Owner Hard Stops D-H1…D-H5, D-C1, D-C3, D-C4, D-C9 | `09` Status APPROVED / Sign-off | CLOSED — ACCEPT RECOMMENDED |
| Feature branch `feature/v67-autonomous-fleet-manager` | `09` D-C9; `10` | CLOSED — BRANCH/GIT |
| Phase 1 ZERO DDL + safety gates | `14` Phase 1 gates | CLOSED |
| Phase 1.1 Bugbot findings 1–3 | `15`; `16` gates | CLOSED — CODE (already shipped) |
| Full Backend suite after 1.1 | `15` / `16` — **1696 passed, 0 failed** | CLOSED — TEST |
| Phase 1.1 residual risks (empty parallel pool schedules sequential; poll no invented cooldown) | `15` § Remaining risks | NOT Phase 2 start blockers |

---

## 2. Classification + resolution plan

### B1 — Explicit owner command

| Field | Content |
|---|---|
| **Class** | OWNER_DECISION |
| **Source** | `14` Unresolved #1; `16` Blockers #1; `10` Recommended next; `15` Phase 2 |
| **Why it blocks** | Phase 2 implementation is forbidden until the owner issues the exact start phrase. Docs explicitly say Phase 2 must not start without it. |
| **Recommended resolution** | Owner sends exactly: `Execute V67.1 Phase 2` |
| **Code/DB change required?** | No (command only) |
| **Owner approval required?** | Yes — the start command itself |
| **Closure status** | **OPEN** — sole remaining start gate. Does **not** prevent declaring documentation readiness; prevents starting implementation. |

---

### B2 — DDL design freeze (`fleet_accounts`)

| Field | Content |
|---|---|
| **Class** | DOCUMENTATION_ONLY (freeze) / DATABASE_PREREQUISITE (apply = Phase 2 work) |
| **Source** | `14` Unresolved #2 + Proposed Phase 2 DDL; `05` §3; `06` H4/B5; `09` D-H4 |
| **Why it blocks** | Phase 2 must not invent schema ad hoc; columns/indexes must be frozen before Alembic revisions land. |
| **Recommended resolution** | Freeze design **now** from approved D-H4 + `05`/`07` (below). Applying DDL is Phase 2 execution, not a pre-start undecided item. |
| **Code/DB change required to close readiness?** | No |
| **Owner approval required?** | No new decision — D-H4 already APPROVED: `Separate fleet_accounts` |
| **Closure status** | **CLOSED** (documentation freeze) |

#### Frozen `fleet_accounts` design (NOT applied)

Authority: D-H4 Recommended + `05` §3 + `07` (FleetState authority).

| Element | Frozen value |
|---|---|
| Table | `fleet_accounts` (separate from `accounts`) |
| Identity | `id` PK; `account_id` FK → `accounts.id`; **UNIQUE(account_id)** |
| Canonical state | `fleet_state` (AFM decision truth per `07`) |
| Policy / journey links | `policy_id` (nullable FK/ref); `journey_id` (nullable) |
| Risk | `risk_budget` (independent axis per `07`) |
| Scores / evidence | JSON scores blob (as proposed in `05`); no fabricated maturity from calendar age |
| Certificate | `certificate_id` nullable (Device/Maturity later phases) |
| Cutover flag | `cutover` boolean default false (per `08` cutover note) |
| Timestamps | `created_at`, `updated_at` |
| Indexes | UNIQUE(account_id); index on `(fleet_state)`; index on `(cutover, fleet_state)` for planner filters |

#### Optional activity cache columns (deferred)

| Decision | Frozen |
|---|---|
| Phase 2 mandatory? | **No** — Phase 1 `activity_evidence.py` remains ZERO-DDL source of truth |
| If added later | Optional denormalized first/last inbound/outbound, unique chat counts on `fleet_accounts` or `fleet_metrics_daily` (`05` §3) |
| Backfill | Idempotent only; historical unknown stays unknown |

**Do not apply any of the above until Phase 2 execution is authorized.**

---

### B3 — Alembic vs `main.py` startup DDL

| Field | Content |
|---|---|
| **Class** | DOCUMENTATION_ONLY (plan freeze) / CODE_PREREQUISITE + DATABASE_PREREQUISITE (implementation = Phase 2) |
| **Source** | `14` Unresolved #3; `16` #3; `05` §2; `06` H5 + B5; `09` D-H5 |
| **Why it blocks** | Large fleet DDL cannot land safely without versioned up/down revisions on a DB already patched by startup SQL. |
| **Recommended resolution** | Freeze plan **now** per D-H5 Recommended (`Yes`) and `06` B5. Implementing Alembic **is** Phase 2 work, not an unresolved owner question. |
| **Code/DB change required to close readiness?** | No |
| **Owner approval required?** | No new decision — D-H5 APPROVED |
| **Closure status** | **CLOSED** (plan freeze) |

#### Frozen Alembic introduction plan (NOT executed)

1. Enable Alembic operationally; every revision has **upgrade + downgrade**.
2. First revision: `v67_01_baseline_stamp` — no-op upgrade; stamp current production schema inventory (models + `main.py` DDL + explicit `instance_live_state`).
3. Freeze **new** growth in `main.py` DDL; hybrid `IF NOT EXISTS` safety net ≤ one release (`06` B5 / D-H5).
4. Then additive `fleet_*` revisions per `05` §6 names (policies → accounts/journeys → …).
5. Downgrade drops only new fleet objects; never destroy `warmup_*`.

---

### B4 — Day-ladder migration (D-H2)

| Field | Content |
|---|---|
| **Class** | DOCUMENTATION_ONLY (scope freeze) / CODE_PREREQUISITE (runtime mapping = Phase 2+ implementation) |
| **Source** | `14` Unresolved #4; `16` #4; `09` D-H2; `06` H2/C8; `07` day ladder |
| **Why it blocks** | Wrong Day-10 / GRADUATED mapping would make FleetState lie about campaign readiness. |
| **Recommended resolution** | Freeze Phase 2 **authority + mapping rules** now. Do **not** require full runtime Day-10 migration or UI Persian copy rewrite before Phase 2 may start. Phase 2 implements adapter mapping when writing `fleet_accounts.fleet_state`; legacy mesh day semantics remain until cutover. |
| **Code/DB change required to close readiness?** | No |
| **Owner approval required?** | No new decision — D-H2 APPROVED |
| **Closure status** | **CLOSED** (scope freeze) |

#### Frozen day-ladder rules for Phase 2+

Exact D-H2 Recommended (unchanged):  
`Yes — adopt V67 ladder; grandfather general mesh GRADUATED (≥25) as CAMPAIGN_READY if clean`

| Rule | Frozen |
|---|---|
| Day 10 (CONSERVATIVE) | Enter / remain `WARMUP_READY` only (`07`) |
| Campaign pool | Only after `GRADUATION_TRIAL` → `CAMPAIGN_READY` |
| Recovery “GRADUATED” (~day 12) | Map to Fleet `WARMUP_READY` (not campaign) |
| General mesh GRADUATED (≥25), incident-clean | Grandfather `CAMPAIGN_READY` |
| Phase 2 start | Create storage + adapter; **no** mandatory live Day-10 rebrand of all enrollments on day one |
| UI / Persian graduation copy | Later phase with Fleet UI — not a Phase 2 start blocker |

---

### B5 — Mesh cutover / canary (D-H1)

| Field | Content |
|---|---|
| **Class** | DOCUMENTATION_ONLY (out-of-scope freeze) |
| **Source** | `14` Unresolved #5; `16` #5; `09` D-H1; `15` Phase 2 not started |
| **Why listed** | Premature mesh delete or Autopilot-on-mesh would violate Hybrid WRAP. |
| **Recommended resolution** | Confirm Phase 2 **does not** cut over or deprecate mesh. Keep WRAP: `mesh_autochat_enabled` default OFF; existing enrollments untouched; deprecate only after canary (later phases). |
| **Code/DB change required to close readiness?** | No |
| **Owner approval required?** | No new decision — D-H1 APPROVED |
| **Closure status** | **CLOSED** — not a Phase 2 start blocker; explicitly **out of Phase 2 scope** |

Exact D-H1 Recommended (unchanged):  
`Hybrid WRAP; mesh default OFF for new Autopilot journeys; existing enrollments continue until cutover; deprecate after canary`

---

### B6 — Live-state policy

| Field | Content |
|---|---|
| **Class** | DOCUMENTATION_ONLY |
| **Source** | `14` Unresolved #6; Phase 1 impl note in `11` |
| **Why listed** | Strict `require_live_state=True` everywhere bricked workers / tests; tightening too early reopens regressions. |
| **Recommended resolution** | Freeze Phase 2 default: keep `automated_require_live_state=False` until FleetState + live hydration is proven reliable; keep `require_live_state=True` available for strict unit paths. Tightening requires a later explicit change (not silent). |
| **Code/DB change required to close readiness?** | No |
| **Owner approval required?** | No (operational freeze; no Decision ID required for keeping Phase 1 default) |
| **Closure status** | **CLOSED** |

---

## 3. Classification summary

| ID | Class | Pre-start status |
|---|---|---|
| B1 | OWNER_DECISION | **OPEN** (start command) |
| B2 | DOCUMENTATION_ONLY → CLOSED; DB apply = Phase 2 | CLOSED |
| B3 | DOCUMENTATION_ONLY → CLOSED; code/DB = Phase 2 | CLOSED |
| B4 | DOCUMENTATION_ONLY → CLOSED; mapping code = Phase 2+ | CLOSED |
| B5 | DOCUMENTATION_ONLY / out of Phase 2 scope | CLOSED |
| B6 | DOCUMENTATION_ONLY | CLOSED |

| Prerequisite class | Items | Status |
|---|---|---|
| OWNER_DECISION (architecture) | D-H1…D-H5, D-C1, D-C3, D-C4, D-C9 | CLOSED in `09` |
| OWNER_DECISION (start) | B1 command | OPEN |
| DOCUMENTATION_ONLY | B2–B6 freezes | CLOSED this pass |
| CODE_PREREQUISITE | Phase 1 + 1.1 safety | CLOSED (shipped) |
| DATABASE_PREREQUISITE | Apply Alembic/`fleet_accounts` | Deferred to Phase 2 execution |
| BRANCH/GIT_PREREQUISITE | Feature branch | CLOSED |
| TEST_PREREQUISITE | 1696 passed / 0 failed | CLOSED |

---

## 4. What this pass changed

| Action | Result |
|---|---|
| Created this file | `17-phase2-blocker-closure.md` |
| Created | `18-phase2-final-readiness.md` |
| Updated | `14-phase2-readiness.md`, `16-phase2-readiness-after-bugfix.md` (point to closure) |
| Code / migrations / tests / Green API / commits | **None** |

---

## 5. Verdict pointer

See `18-phase2-final-readiness.md`.
