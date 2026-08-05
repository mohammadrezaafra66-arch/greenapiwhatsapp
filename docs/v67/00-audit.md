# V67.1 Phase 0 — Read-Only Audit

**Status:** Complete (audit only; no code/DB/Green API changes)  
**Branch inspected:** `main` (ahead of `origin/main` by 12 commits; tip `c1b1f40` V65)  
**Other branches:** `afrapayam-redesign`, `remotes/origin/claude/whatsapp-group-voice-v26-k93pir`  
**Date:** 2026-08-05

## Summary

The codebase already contains a large warm-up / mesh / Team Collaboration / campaign stack that covers many *pieces* of V67.1 (send gate, incidents, webhooks, Celery ticks, price cache, helpers, recovery). It does **not** contain an Autonomous Fleet Manager, the V67.1 fleet state machine, Trust/Risk/Capacity engines, Device Registry, Maturity Certificate, Shadow/Canary, or Decision Explainer. Three parallel state spaces already exist (`AccountStatus`, `WarmupState`, Green API live state). Migration strategy is `create_all` + idempotent `ALTER` in `main.py`, not Alembic versioned up/down scripts.

## 1. Branches

| Branch | Relevance |
|---|---|
| `main` | Primary; V17–V65 warm-up, mesh, TC, campaign multi-account, suspension incidents |
| `afrapayam-redesign` | UI redesign; not fleet AFM |
| `origin/claude/whatsapp-group-voice-v26-k93pir` | Group voice; orthogonal |

No dedicated `v67` / fleet branch exists.

## 2. Accounts

**Model:** `backend/app/models/account.py` — `Account`, `AccountStatus`

| Field / concept | Present? | Notes |
|---|---|---|
| `status` | Yes | `active`, `banned`, `disconnected`, `pending`, `deleted`, `suspended`, `green_api_deleted` |
| `connected_at` | Yes (V39) | Universal 24h connect cooldown anchor |
| `reconnected_at` | Yes (V38) | Legacy; still stamped; gate prefers `connected_at` |
| `authorized_at` | Yes | Telegram / first-auth |
| `suspended_until` | Yes (V57) | From `getWaSettings.suspendedUntil` |
| `sent_today` / `received_today` | Yes | Daily counters; not `total_daily_flow` policy object |
| `days_active` | Yes | Drives `computed_daily_limit`; days &lt; 10 hard-cap 5 |
| `incident_count_7d` / `last_incident_at` | Yes | Updated by incident handler |
| `throttle_*` / `cooldown_until` | Yes | Yellow-card governors |
| `auto_warmup` / `warmup_*` / `is_warm_peer` | Yes | Legacy + mesh peer mark |
| `first_activity` / first inbound / last outbound | **No** as dedicated fields | Enrollment has `last_activity_at` only |
| Fleet states (`NEW`…`REWARM_REQUIRED`) | **No** | |

**Overview aggregation:** `backend/app/services/accounts_overview.py`, API used by `AccountsOverview.jsx`.

## 3. Warm-up / Mesh

**State machine:** `backend/app/services/warmup_state.py`

```
ENROLLED → COOLDOWN → RECEIVING → REPLYING → RAMPING → MATURING → GRADUATED
Side: PAUSED | YELLOWCARD | BLOCKED_RESET
```

**Schedule:** `backend/app/services/warmup_scheduler.py`

- General: day 1 cooldown; 2–3 receiving; 4 reply; 5–10 ramp; 11–24 maturing; **≥25 GRADUATED**
- Recovery (V41): day 1 cooldown; 2–4 receiving; 5 reply; ramp; **≥12 GRADUATED**
- Ramp curve hardcoded: `[12, 20, 32, 48, 66, 84, 100]`
- Peers: `peers_per_new_number_min=3`, `max=6` (implies ~1:3–1:6)

**Data:** `backend/app/models/warmup_mesh.py` — `WarmupEnrollment`, `WarmupMeshEdge`, `WarmupEventLog`, group targets/memberships, link vault

**Engine / services (selected):**

| File | Role |
|---|---|
| `warmup_engine.py` | Tick; `next_action_at` jitter; mesh send plan |
| `warmup_mesh_service.py` | Edges, handshake, `getWaSettings` phone fallback |
| `warmup_killswitch.py` | Yellow rest, block reset, chain-ban breaker (2 / 48h) |
| `warmup_peer_eligibility.py` | ≥14d clean peer bar |
| `warmup_warmth.py` | Warmth score (age + incidents + activity) |
| `warmup_recovery_enroll.py` / `warmup_recovery_autoenroll.py` | Recovery enroll + Path B |
| `warmup_auto.py` | Older managed auto warm-up |
| `warmup_group_engine.py` | Additive group placement |
| `typing_sim.py` + `GreenAPIClient.set_warming_instance_settings` | `autoTyping:2`, SendTyping fallback |

**Celery:** `process-mesh-warmup` every 180s; `warmup-safety-scan` 6h; group/helper/cold-reply/team-schedule ticks (see `celery_app.py`).

## 4. Team Collaboration / Human helpers

**Models:** `backend/app/models/warmup_helpers.py` — helpers, tasks, config, sender config, logs  
**Services:** `warmup_helper_engine.py`, `warmup_helper_service.py`, `warmup_team_schedule.py`, `warmup_cold_reply.py`, `sender_eligibility.py`  
**UI:** `frontend/src/pages/TeamCollaboration.jsx`  
**Approx. V67 mapping:** helpers ≈ `HUMAN_PARTICIPANT` (system asks; humans send); connected warm accounts ≈ `CONNECTED_WARMER_ACCOUNT`. Missing: `consent`, `native_contact_verified`, reliability score, explicit participant type enum.

## 5. Onboarding (QR / 24h gates)

**Model:** `backend/app/models/account_onboarding.py`  
**Service:** `onboarding_service.py` — Gate A SIM→WA 24h; Gate B WA→Green API 24h  
**UI:** `Onboarding.jsx`  
Closest existing analogue to V67 `QR_WAITING` / `READY_TO_LINK`, but separate from mesh enrollment and fleet states.

## 6. Green API client

**File:** `backend/app/services/green_api.py` — `GreenAPIClient`

Present: `get_state` / `getStateInstance`, `get_settings` / `set_settings`, `get_wa_settings`, `set_webhook` (includes `stateWebhook`), `send_message`, queue show/clear, `send_typing` / `send_typing_ms`, `set_warming_instance_settings` (`autoTyping:2`), partner helpers, per-instance HTTP circuit breaker.

Partner: `green_partner.py`.

## 7. Webhooks

**File:** `backend/app/api/v1/webhook.py`

- Dedup (V65): Redis key `instance + typeWebhook + idMessage + status`, NX 86400s
- Handles: `incomingMessageReceived`, `stateInstanceChanged`, `outgoingMessageStatus`, calls, blocks, quota, device, catalog, buttons, polls
- `stateInstanceChanged`: updates `send_gate` live cache; maps blocked/notAuthorized/authorized/yellowCard/suspended; calls `record_suspension` + `refresh_suspended_until`; routes to `warmup_killswitch`
- STOP/opt-out: `optout.is_opt_out` → blacklist + `OptOutLog`
- Incoming block → auto-blacklist

**Gap:** events without `idMessage` skip dedup; no durable event ledger for AFM.

## 8. Send gate / governors / FanOut

| Component | Path | Behavior |
|---|---|---|
| Pre-send gate | `send_gate.py` | `can_send_now` / `gate_check`: active, connect cooldown 24h, cooldown, throttle, live blocking states incl. `suspended` |
| Governors | `governors.py` | Daily hard cap 200, warmup new-contact 20/day, delay floor 500ms / default 15000ms |
| FanOutGuard | `account_selection.py` | Fail-closed campaign selection; never expand beyond user pick |
| Peer pacer | `peer_pacer.py` | Process-local 10–15s per sending instance |
| Sender eligibility | `sender_eligibility.py` | TC sender ≥14d + clean; recovery hard-block |

## 9. Celery / Redis / locks

**App:** `backend/app/workers/celery_app.py` — queues: campaigns, sending, webhooks, extraction, backfill, celery; timezone Asia/Tehran  
**Tasks:** `backend/app/workers/tasks.py`

Notable beat jobs: mesh 180s, TC schedule 300s, poll states 60s, yellow cards 120s, campaign orphan recovery 600s, quality/reply monitors hourly.

**Locks:**

- Campaign: `campaign_lock:{id}` Redis SET NX 4h — **fail-open if Redis down**
- Webhook dedup: Redis NX
- Rate limit: `redis_rate_limiter.py` day/hour counters
- Mesh: `next_action_at` per enrollment; **no** Redis atomic claim key `account_id+journey_id+action_type+scheduled_slot`

## 10. Campaigns

**Model:** `campaign.py` — PV/group scope, parallel, `selected_account_ids` (V60), weekday restrict, per-instance cap, typing_simulation, product pool (V63), opt-out text  
**Runner:** `campaign_runner.py`, `group_campaign_runner.py`  
**Capacity UI:** `frontend/src/pages/campaignCapacity.js`  
**Brakes:** send_gate + governors + FanOut + weekday preflight

No fleet autopilot planner; no Risk Budget; no graduation trial pool.

## 11. Incidents

**Model:** `AccountIncident` in `incident.py`  
**Handler:** `incident_handler.py` — `handle_yellow_card`, `record_suspension` / `resolve_suspension` (V65), `apply_warning_throttle`

| Signal | Account status | Incident row? |
|---|---|---|
| yellowCard | cooldown + throttle | Yes |
| suspended | `suspended` + `suspended_until` | Yes (V65) |
| blocked | `banned` | **No dedicated AccountIncident writer found** |
| notAuthorized / forced logout | `disconnected` | **No dedicated AccountIncident** (mesh killswitch may reset enrollment) |

## 12. Metrics / scores (existing, not V67 five-engine)

| Score | File | Inputs |
|---|---|---|
| Health | `account_health.py` | Remaining capacity + yellow rate |
| Quality | `quality_score.py` | Campaign reply + failure rates |
| Warmth | `warmup_warmth.py` | Age, incidents, activity |
| Reply ratio (mesh) | `warmup_state.compute_reply_ratio` | received/sent |

Missing V67: Trust, Risk, Activity, Compliance as named engines; `unique_inbound_chats`, `bidirectional_chats`, `conversation_ratio`, Policy-driven `total_daily_flow`.

## 13. Product / price / AI

- `price_service.py` — Supabase; Redis cache TTL ≤60s via `settings.price_cache_seconds` (clamped to max 60). Note: `config.py` also defines unused/legacy `pricing_cache_minutes=5` — do not treat that as the live TTL.
- Campaign product pool V63; AI merge / message generation for campaigns and mesh
- AI key pool: `ai_key_pool.py`, pages `AiKeys.jsx` / `AiSettings.jsx`
- AI does not own send decision for gates (gates are rule-based) — aligns with V67 “AI suggests; rules decide” for send safety, but no DecisionExplainer
- Cross-ledger outbound count: `send_metrics.real_sent_today` / `real_sent_today_by_account` (campaign + helper + mesh + status)
- Volume spike guard: `volume_guard.effective_daily_cap_guarded` (≤4× trailing 7d avg; floor 20)

## 14. Frontend (fleet-relevant)

Present: Dashboard, Accounts, AccountsOverview, Warmup, TeamCollaboration, Onboarding, Campaigns, Protection, Blacklist, SendQueue, Capabilities, Reporting  
Absent: Fleet Dashboard, Policies, Human Participants (as named), Incidents fleet view (Protection is partial), Simulations, Decisions, Audit trail UI, Autopilot enable flow

## 15. Tests (sample of relevant)

~198 backend test modules. High coverage for V17–V65 warm-up/mesh/TC/gate/campaign pieces, e.g.:

- `test_v65_webhook_dedup_and_suspension.py`
- `test_v60_step*.py`, `test_v39_*.py`, `test_v41_*.py`, `test_v27_*.py`, `test_v21_ratio_cap.py`
- `test_campaign_lock.py`, `test_redis_rate_limiter.py`

No V67 AFM / journey / shadow / canary suite.

## 16. Schema / migrations

- `backend/migrations/env.py` notes tables normally via `Base.metadata.create_all`
- Large idempotent DDL block in `backend/app/main.py` startup (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`)
- **No Alembic revision chain with down scripts** (V67 Phase 2 requirement conflict)
- `InstanceLiveState` (`instance_live_state`) is an ORM model used by `send_gate.persist_live_state` but has **no** matching `CREATE TABLE` in `main.py` — durability depends on `create_all` / best-effort upsert; treat as a Phase 2 inventory item

## 16b. Feature flags

- Present operational toggles: mesh enroll, warm-peer, TC sender, `typing_simulation`, mesh breaker API, `auto_failover_on_yellow_card` (default False)
- **Absent:** `AFM_*` / Autopilot / Shadow / Canary / Policy-version feature flags

## 17. Hard stops surfaced by this audit

See `03-conflict-map.md` for full list. Highest severity:

1. Mesh AI chat between own numbers vs V67 ban on artificial interaction loops  
2. Day-10 / GRADUATED semantics vs V67 `WARMUP_READY` only  
3. Hardcoded ramp 12→100 vs Policy-only rule  
4. Triple state space without adapter  
5. Fail-open campaign lock vs required atomic claim  
6. No versioned up/down migrations  

## 18. Phase 0 outputs

| Doc | Purpose |
|---|---|
| `00-audit.md` | This inventory |
| `01-existing-capability-map.md` | Capability → exact symbols |
| `02-gap-analysis.md` | Missing vs V67.1 |
| `03-conflict-map.md` | Contradictions / hard stops |
| `04-reuse-plan.md` | Adapter/wrapper reuse |
| `05-migration-plan.md` | Proposed schema/cutover (plan only) |

**Acceptance:** No application code, DB, Green API, accounts, webhooks, queues, or campaigns were modified. Only `docs/v67/*` created.
