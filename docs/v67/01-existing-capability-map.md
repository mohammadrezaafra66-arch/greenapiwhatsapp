# V67.1 Phase 0 — Existing Capability Map

Maps each V67.1 intended capability to **exact reusable components** already in the repo.  
Legend: **R** = reuse as-is (adapter wrap) · **A** = adapt · **P** = partial · **N** = none

## 1. Manager engines (V67 section 4)

| V67 component | Status | Exact reuse |
|---|---|---|
| AccountClassifier | N/P | Closest: `onboarding_service` gates + `WarmupEnrollment.state` + `Account.status` + `sender_eligibility.evaluate` — no single classifier |
| JourneyOrchestrator | N/P | `warmup_engine.run_warmup_tick` + `warmup_scheduler.target_state_for_day` + TC `warmup_team_schedule.run_team_schedule_tick` — day-index journeys, not V67 journey IDs |
| PolicyEngine | N | `WarmupConfig` dataclass defaults only; campaign fields are per-campaign knobs, not versioned policies |
| TrustEngine | N | Fragments in `warmup_warmth`, `quality_score`, `account_health` |
| RiskEngine | N | Fragments in `incident_handler`, `warmup_killswitch`, `send_gate.BLOCKING_LIVE_STATES` |
| CapacityPlanner | P | `Account.computed_daily_limit`, `governors.effective_daily_cap`, `volume_guard.effective_daily_cap_guarded`, `send_metrics.real_sent_today*`, dashboard capacity, `campaignCapacity.js`, V60 per-instance cap |
| ActionPlanner | P | Mesh `plan` in `warmup_engine`; helper task planner; no unified action ledger |
| CampaignPlanner | P | Manual campaign create + `campaign_runner` / parallel path; no fleet autopilot |
| ContactEligibilityEngine | P | Blacklist, opt-out, contact groups, active contacts, campaign contact status |
| GraduationGate | P | `WarmupState.GRADUATED` at day 25 (or recovery day 12) — **conflicts** with V67 day-10 `WARMUP_READY` |
| RecoveryManager | P | `warmup_recovery_enroll`, `recovery_disruption_reset`, `record_suspension`, killswitch `BLOCKED_RESET` |
| MaintenanceManager | P | Graduated → campaigns only; `keepwarm_max_idle_days=10` in config; safety scan idle 14/30d |
| DecisionExplainer | N | Some Persian reason strings (`sender_eligibility`, FanOut abort reasons); no versioned decision log |

## 2. Green API / telemetry

| Capability | Status | Symbol |
|---|---|---|
| stateInstanceChanged | R | `webhook.handle_state_change` |
| getWaSettings + suspendedUntil | R | `GreenAPIClient.get_wa_settings`; `state_monitor.refresh_suspended_until`; `Account.suspended_until` |
| getSettings / setSettings | R | `get_settings` / `set_settings`; `set_webhook`; `set_warming_instance_settings` |
| getStateInstance health | R | `get_state`; Celery `poll_instance_states`; `InstanceLiveState` model |
| autoTyping preferred | R | `set_warming_instance_settings` → `autoTyping: "2"` |
| SendTyping fallback | R | `send_typing`, `send_typing_ms`; `typing_sim.apply_typing_simulation` |
| Queue show/clear | R | `show_messages_queue`, `clear_messages_queue` (used in yellow-card handler) |
| Webhook-only receive | R | Documented in client/settings; polling separate flag |

## 3. Scheduling / locks / idempotency

| Capability | Status | Symbol |
|---|---|---|
| Planner tick ~5 min | P | TC schedule 300s; mesh 180s; status schedules 300s — not one AFM tick |
| `next_action_at` + jitter | R | `WarmupEnrollment.next_action_at`; `warmup_scheduler.schedule_next_action`; helper `next_ask_at` |
| Skip missed / no catch-up | P | Mesh defers via `next_action_at`; not explicit “skip missed slot” ledger rule |
| Atomic claim + Redis lock | P | `campaign_lock:{id}` (fail-open); webhook Redis dedup; **no** action-slot claim key |
| Idempotency key pattern | P | Webhook dedup; helper task UniqueConstraint; campaign message id on contacts |

## 4. Safety / circuit breakers

| Capability | Status | Symbol |
|---|---|---|
| Pre-send health gate | R | `send_gate.gate_check` / `can_send_now` |
| Fan-out guard | R | `account_selection.FanOutGuardError` / `resolve_sending_accounts` |
| Mesh chain-ban breaker | A | `warmup_killswitch` — threshold 2 / **48h** (V67 wants 2 Suspend / **24h** fleet stop) |
| HTTP client breaker | A | `GreenAPIClient._guarded` per-instance failure accounting |
| Telegram breaker | A | `telegram_warmup.py` (platform-specific) |
| Yellow-card auto response | R | `incident_handler.handle_yellow_card` |
| Suspension incident | R | `record_suspension` / `resolve_suspension` (V65) |
| STOP / blacklist | R | `optout.is_opt_out`; `api/v1/blacklist.py`; webhook block handler |

## 5. Human / native contacts

| Capability | Status | Symbol |
|---|---|---|
| Human task/reminder | R | `WarmupHelperTask` + helper engine + reminder caps (V33) |
| Connected warmer send | R | Mesh peers + TC senders via own instances |
| Consent evidence | N | No consent field |
| Native phonebook verified | N | Mesh handshake `saved_as_contact_*` is **API addContact**, not phone OS address book proof |
| Reliability | N | No reliability score |

## 6. Device registry

| Capability | Status | Symbol |
|---|---|---|
| device_id / imei_hash / batch | N | Onboarding has `phone_make_model` free text only |
| One primary account per device | N | Not enforced |
| Sequential number cohort | N | Unknown treated nowhere as data model |

## 7. Campaign / product / AI

| Capability | Status | Symbol |
|---|---|---|
| Multi-account pick + capacity | R | V60 `selected_account_ids`, `campaignCapacity.js` |
| Weekday window | R | V60 step 3 |
| Live price ≤60s cache | R | `price_service` uses `price_cache_seconds` (≤60). Ignore legacy `pricing_cache_minutes=5` for AFM contracts |
| Stale/out-of-stock guard | P | In-stock filter on fetch; stale handled via short TTL; need AFM “no send if invalid” orchestration |
| AI structured message | P | Campaign/mesh AI generators exist; no AFM compliance guard wrapper |
| Product pool | R | V63 |

## 8. UI surfaces

| V67 UI | Status | Existing page |
|---|---|---|
| Fleet Dashboard | N | Closest: `Dashboard.jsx` + `AccountsOverview.jsx` |
| Accounts | R | `Accounts.jsx` |
| Human Participants | P | `TeamCollaboration.jsx` |
| Campaign Contacts | P | `Contacts.jsx` / `ContactGroups.jsx` / `ActiveContacts.jsx` |
| Policies | N | — |
| Incidents | P | `Protection.jsx` |
| Simulations | N | — |
| Decisions / Audit | P | TC toggle audit log; `WarmupEventLog`; no fleet decision store |

## 9. Celery task inventory (fleet-relevant)

From `celery_app.beat_schedule` + `tasks.py`:

- `process_mesh_warmup` (180s)
- `process_helper_warmup` (180s)
- `process_cold_replies` (120s)
- `process_team_schedule` (300s)
- `process_thank_yous` (120s)
- `process_group_warmup` (600s)
- `warmup_safety_scan` (6h)
- `process_warmup_accounts` (crontab 9,11,13,16,19)
- `poll_instance_states` (60s)
- `detect_yellow_cards` (120s)
- `sync_account_states` (300s)
- `quality_score_monitor` / `reply_rate_monitor` (hourly)
- `recover_orphaned_campaigns` (600s)
- `run_campaign` / `run_group_campaign` (on demand)

## 10. Reuse principle (locked for later phases)

**Wrapper / Adapter / Orchestrator on top of the symbols above — do not fork a parallel send engine.**  
Healthy paths that must not be deleted before cutover: `send_gate`, `campaign_runner`, mesh tick, TC helper path, webhook processor, price_service, incident_handler.
