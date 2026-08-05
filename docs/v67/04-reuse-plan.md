# V67.1 Phase 0 — Reuse Plan

Principle from master doc: **Wrapper / Adapter / Orchestrator — not a parallel engine.**  
Do not delete healthy services until Shadow → Compare → per-account Cutover → Deprecate.

## 1. Foundation adapters (build first, wrap existing)

| AFM port | Wrap these exact modules | Notes |
|---|---|---|
| `GreenApiAdapter` | `services/green_api.py`, `set_warming_instance_settings`, `state_monitor.refresh_suspended_until` | Thin facade; add contract tests; no second HTTP client |
| `WebhookEventAdapter` | `api/v1/webhook.py` handlers | Emit normalized domain events into AFM bus; keep handlers as source |
| `SendGateAdapter` | `send_gate.gate_check`, `governors.*` | Single pre-send call; AFM never bypasses |
| `IncidentAdapter` | `incident_handler.*`, `AccountIncident` | Extend with block/logout recorders; do not fork table |
| `PriceAdapter` | `price_service.py` | Enforce ≤60s + no-send on invalid |
| `OptOutAdapter` | `optout.py`, blacklist API | Global STOP already exists |

## 2. Journey / warm-up reuse

| AFM concept | Reuse | Adapter strategy |
|---|---|---|
| New-number quiet / inbound / ramp | `warmup_scheduler`, `warmup_engine`, `WarmupEnrollment` | Map WarmupState → FleetState in read model; **writes** go through one orchestrator |
| Recovery / rewarm | `warmup_recovery_enroll`, `recovery_disruption_reset`, killswitch | Become RecoveryManager backends |
| Peer eligibility | `warmup_peer_eligibility`, `warmup_warmth` | Feed Trust/Risk inputs; do not reimplement age math |
| Onboarding 24h QR discipline | `account_onboarding`, `onboarding_service` | Classifier inputs for NEW/QR_WAITING |
| Human participants | `warmup_helpers` models + helper engine | Rename/extend fields (consent, native_verified) via additive columns |
| Group warm-up | `warmup_group_*` | Keep additive; optional Maintenance/Inbound channel |

**Deprecate later (not Phase 0–1):** legacy `warmup_auto.py` / `tasks.process_warmup_accounts` if fully superseded — only after cutover proof.

## 3. Campaign reuse

| AFM concept | Reuse |
|---|---|
| Send execution | `campaign_runner.py`, `group_campaign_runner.py` |
| Account selection | `account_selection.resolve_sending_accounts` + FanOutGuard |
| Capacity display | V60 caps + `campaignCapacity.js` |
| Product pool | V63 pool services |
| Weekday / window | existing campaign preflight |

**CampaignPlanner** should *schedule and constrain* campaigns, not copy the send loop.

## 4. Scoring reuse (inputs only)

Do not invent a fourth health number without mapping:

| Existing | Maps toward |
|---|---|
| `account_health.compute_score` | Health Score component (capacity + yellow) |
| `quality_score.compute_quality_score` | Trust/Risk engagement components |
| `warmup_warmth.compute_warmth` | Trust / peer eligibility |
| `incident_count_7d` + open incidents | Risk Score |
| `sent_today` + `received_today` | Activity + total_daily_flow (extend with unique chats) |
| `send_metrics.real_sent_today*` | Activity / capacity truth across ledgers |
| `volume_guard.spike_capped_volume` | Risk / capacity spike component |

AFM five engines = **new pure functions** reading these inputs + new metrics tables — not replacement of campaign runner.

## 5. Scheduling / lock reuse

| Keep | Change later |
|---|---|
| Celery beat + queue isolation | Add AFM planner task (5 min) **alongside** mesh/TC ticks initially |
| `next_action_at` pattern | Generalize to action ledger |
| `campaign_lock:*` | Model for action claim keys; tighten fail-open |
| Webhook Redis dedup | Keep; add durable event id store |
| `redis_rate_limiter` | Keep as hard ceiling under CapacityPlanner |

**Avoid:** process-local-only pacers (`peer_pacer`) as sole multi-worker safety — wrap with Redis when AFM claims actions.

## 6. Frontend reuse

| Keep Persian pages | AFM UI approach |
|---|---|
| Accounts, AccountsOverview, Warmup, TeamCollaboration, Onboarding, Campaigns, Protection | New Fleet Dashboard **composes** existing APIs first; do not rewrite Warmup/TC in Phase 11 until adapters stable |
| Layout/nav | Additive nav entry; no mass IA break |

All new user-facing strings remain Persian/RTL (product guardrail unchanged).

## 7. Explicit non-reuse (do not clone)

- Do not create a second `GreenAPIClient`
- Do not create a second webhook endpoint
- Do not create a parallel campaign runner
- Do not duplicate opt-out keyword logic
- Do not bypass `gate_check` for “fleet privileged” sends

## 8. Shadow compare plan (feeds Phase 12)

For each enrolled account:

1. Existing mesh/TC/campaign path continues (source of truth for sends until canary)
2. AFM Shadow computes intended state, capacity, and next action
3. Log diffs: state mismatch, cap mismatch, would-send vs did-send
4. Cut over one account after owner approval

## 9. Phase sequencing vs reuse

| Phase | Primary reuse touchpoints |
|---|---|
| 1 | webhook, incident_handler, send_gate, state_monitor, queue API |
| 2 | models + main.py DDL → move to versioned migrations wrapping same tables |
| 3 | green_api + webhook events |
| 4 | warmup_state/scheduler + onboarding (read adapters) |
| 5 | celery_app + redis locks + next_action_at |
| 6 | health/quality/warmth + new engines |
| 7 | warmup_helpers |
| 8 | enrollment GRADUATED semantics (careful) |
| 9 | campaign_runner + price_service |
| 10 | killswitch + recovery_* |
| 11 | frontend compose |
| 12 | new simulation harness around Fake doubles already used in tests |
