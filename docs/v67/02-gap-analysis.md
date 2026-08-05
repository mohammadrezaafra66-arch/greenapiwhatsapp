# V67.1 Phase 0 — Gap Analysis

What V67.1 requires that the current codebase does **not** provide (or only partially provides). Ordered by Phase 1–12 affinity.

## P0 / Phase 1 gaps (critical safety)

| Gap | Evidence | Impact |
|---|---|---|
| Blocked / forced-logout do not always write `AccountIncident` | Webhook sets `banned`/`disconnected`; no `record_block` analogue to `record_suspension` | Health/warmth/eligibility undercount danger |
| No fleet-level circuit breaker (2 Suspend / 24h) | Mesh breaker is 2 / **48h** and mesh-scoped; client breaker is HTTP-scoped | Fleet can keep campaigning after correlated suspensions |
| Queue health not first-class AFM signal | Queue cleared on yellowCard; `api/v1/queue.py` exposes counts; no breaker on backlog | V67 stop condition missing |
| Webhook freshness / stale detection | Live state max age 90s for gate; no fleet “webhook stale → stop” | Silent tunnel death |
| first/last activity + unique chat metrics | Enrollment `last_activity_at` only; account counters are totals | Classifier cannot choose journey by evidence |
| Unhealthy account still selectable in some UI paths | V65 fixed suspension incident; FanOut + gate help; overview may still show warmth until next poll | Operator risk |

## Phase 2 — Data model gaps

Missing tables / entities named in V67 Phase 2:

- `fleet_accounts` (or fleet projection over `accounts`)
- `journeys` / journey instances
- `actions` (action ledger with idempotency unique)
- `metrics` (daily flow, unique chats, bidirectional)
- `policies` (CONSERVATIVE/BALANCED/EXPERIMENTAL versioned)
- `humans` / human_participants (consent, native_contact_verified, hours, reliability)
- `device_registry`
- `certificates` (maturity)
- `capacity_decisions` + decision audit

Existing: `accounts`, `warmup_enrollment`, `warmup_mesh_edge`, `warmup_event_log`, `warmup_helper*`, `account_incidents`, `account_onboarding`, `instance_live_state` (ORM + `create_all` only; no explicit `main.py` DDL), campaigns/contacts, `daily_send_logs` (feeds `volume_guard`).

**Migration tooling gap:** no Alembic up/down revisions; startup DDL only.

## Phase 3 — Green API adapter gaps

| Need | Gap |
|---|---|
| Unified Green API Adapter for AFM | Logic scattered across `green_api.py`, webhook, `state_monitor`, warmup settings |
| Contract tests for suspendedUntil / yellowCard mapping | Partial unit tests (V57/V65); no AFM contract suite |
| Event dedup durable ledger | Redis TTL 24h only |
| Enforce autoTyping on all send paths | Warming settings helper exists; campaign typing is optional flag |

## Phase 4 — Classifier / Journey gaps

| V67 state | Existing analogue | Gap |
|---|---|---|
| NEW / PRECHECK | onboarding step 1 | Not linked to fleet |
| QR_WAITING / READY_TO_LINK | onboarding Gate B + QR APIs | No automatic state machine |
| AUTHORIZED_QUIET | connect cooldown + COOLDOWN | Naming/semantics diverge |
| INBOUND_BUILDING | RECEIVING | Mesh peers generate inbound (may violate “real only”) |
| BIDIRECTIONAL_BUILDING | REPLYING | Same |
| CONTROLLED_RAMP | RAMPING | Hardcoded curve |
| WARMUP_READY | **none** (day 10 is still RAMPING or end of ramp → MATURING) | Day 10 currently not a campaign-forbidden named gate |
| GRADUATION_TRIAL | **none** | Graduates straight to GRADUATED |
| CAMPAIGN_READY / MATURE | GRADUATED / days_active | Collapsed |
| MAINTENANCE / AT_RISK | idle safety scan / quality throttle | Incomplete |
| SUSPENDED / BLOCKED / FORCED_LOGOUT / RECOVERY_COOLDOWN / REWARM_REQUIRED / FAILED / RETIRED | partial status + BLOCKED_RESET | No unified fleet enums |

## Phase 5 — Scheduler gaps

- No single 5-minute AFM planner tick owning all journeys
- No idempotency key `account_id + journey_id + action_type + scheduled_slot`
- No dead-letter queue for failed actions
- Campaign lock fail-open on Redis outage
- Peer pacer is **in-process memory** (multi-worker unsafe for gap enforcement)

## Phase 6 — Trust / Risk / Capacity gaps

Missing as first-class engines:

- Trust Score (active days, unique contacts, inbound-initiated, bidirectional, delivery)
- Risk Score (incident, volume jump, low reply, repetitive content, device reuse, inactivity)
- Activity Score / Compliance Score
- Risk Budget ladder: `NORMAL → SLOW → RECEIVE_ONLY → PAUSED → REWARM_REQUIRED`
- Dynamic capacity from total daily flow policy (not hard-coded ramp)
- Decision explanation records

## Phase 7 — Human / native contact gaps

- No `consent` evidence store
- No `native_contact_verified` (OS address book)
- No reliability scoring / cooldown fields as V67 specifies
- Helper model cannot express “system must never send as the human”

## Phase 8 — Graduation / maintenance gaps

- No Maturity Certificate checklist
- No Graduation Trial pool
- Day 10 ≠ `WARMUP_READY`
- Maintenance “few real daily interactions” not automated as V67 maintenance manager

## Phase 9 — Campaign autopilot gaps

- No orchestrated pipeline: fleet health → risk budget → capacity → eligible contacts → live price → AI → compliance → schedule → feedback → breaker
- Manual campaign launch remains the control plane
- No Shadow / Canary gates before real send

## Phase 10 — Recovery gaps

- Suspend path: stop outbound + `suspended_until` **partially** present; no automatic `REWARM_REQUIRED` fleet state after cooldown verify
- Block/logout: mesh `BLOCKED_RESET` exists; fleet traceable rewarm incomplete
- Direct resume after suspend still possible if status flipped without rewarm enrollment

## Phase 11 — Dashboard gaps

No RTL fleet pages for: pools, journey timeline, five scores, capacity decisions, simulations, cohort stats, decision reasons as primary UX.

## Phase 12 — Simulation / Shadow / Canary / Cohort gaps

| Need | Status |
|---|---|
| Virtual clock | N |
| Fake Green API | Partial test doubles only |
| Synthetic webhooks / fault injection | N as product |
| Shadow mode | N |
| Canary 1–2 accounts | N |
| Cohort sequential-number experiment | N (Unknown explicitly) |
| Owner approval gate for real send | N |

## Metrics gaps (V67 section 7)

Not computed as durable daily metrics:

- `total_daily_flow` as policy object (only raw sent/received counters)
- `unique_inbound_chats` / `unique_outbound_chats`
- `bidirectional_chats`
- `replying_contact_ratio`
- `conversation_ratio`

## Security / governance gaps vs V67

- Token stays backend-only (**good**; keep)
- No RBAC beyond single-admin assumption (`DEFAULT_OVERRIDER = "admin"`)
- No retention policy engine for PII/consent
- Audit exists in fragments (TC log, event log, incidents) — not unified AFM audit

## Summary count

| Category | Missing | Partial | Reusable core |
|---|---|---|---|
| Engines | 8+ | 5 | 0 complete AFM engines |
| States | ~15 fleet states | ~10 mapped loosely | Warmup + Account status |
| Safety P0 | 4–6 | several | send_gate, webhook, incidents |
| Data tables | ~9 | — | many related tables |
| Simulation/Canary | nearly all | — | unit FakeSession only |
