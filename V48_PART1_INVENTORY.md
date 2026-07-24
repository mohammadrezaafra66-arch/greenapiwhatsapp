# V48 PART 1 — Inventory of the four existing account-data sources

Findings note (no code change). Confirms the EXACT backend functions each of the four
pages calls, so the new unified overview (PART 2) can reuse them identically rather than
reimplementing any scoring/eligibility/incident logic.

## 1. `/accounts` (Accounts.jsx)
- Frontend call: `Accounts.list()` → `GET /api/v1/accounts/` → `accounts.list_accounts()`.
- Per-account shape (source of truth for connection state + activity):
  `id, name, instance_id, phone, status, sent_today, received_today,
   daily_limit(=computed_daily_limit), days_active, warmup_enrolled, warmup_state,
   is_warm_peer, is_listener, platform`.
- Role inputs it uses: `warmup_exclusion.enrollment_states_by_instance(db)` →
  `{instance_id: (state, is_enabled)}`.
- Scope: `Account.status != deleted`, ordered by `created_at desc`.

## 2. `/warmup` (Warmup.jsx) — mesh dashboard + warmth
- Frontend call: `WarmupApi.meshDashboard()` → `GET /api/v1/warmup/mesh-dashboard`
  → `warmup.mesh_dashboard()` → `warmup_dashboard.build_dashboard(...)`.
- **Authoritative ROLE logic** (warmup.py mesh_dashboard, per active account):
  - `being_warmed`  = enrolled AND is_enabled AND state != GRADUATED
  - `peer_sender`   = `is_warm_peer`
  - `graduated_peer`= enrolled AND state == GRADUATED
  - `none`          = otherwise
  (`GRADUATED = warmup_exclusion.GRADUATED = WarmupState.GRADUATED.value`.)
- **Warmth score** is served separately by Team Collaboration endpoints (below); the mesh
  dashboard itself shows warm-up state/day/progress, not the 0–100 score.

## 3. `/protection` (Protection.jsx) — incident history + health
- Frontend call: `IncidentsApi.protection()` → `GET /api/v1/incidents/protection`
  → `incidents.protection()`.
- Per-account: `health_score(=account_health.health_breakdown()["score"], 0.0 if in_cooldown),
  sent_today, effective_cap(=governors.effective_daily_cap), yellow_card_rate_7d,
  reply_rate_7d, throttle_factor, throttle_until, in_cooldown, cooldown_until,
  incident_count_7d, status, green_api_deleted`.
- `health_breakdown(account, db)` (account_health.py) → `score, daily_limit, sent_today,
  remaining_capacity, capacity_ratio, sends_7d, yellow_card_7d, yellow_card_rate`.
- Incident timeline: `IncidentsApi.list()` → `GET /api/v1/incidents/` →
  `incidents.list_incidents()` reads `AccountIncident` (type, severity, created_at, resolved).
- Scope: `Account.status != deleted`.

## 4. `/team-collaboration` (TeamCollaboration.jsx) — role (TC) + eligibility + warmth
- Warmth badges: `WarmupHelpersApi.warmth()` → `GET /warmup-helpers/warmth`
  → `warmup_warmth.warmth_for_all_senders(db)` (per account: `warmth_for_account`).
- Sender list / TC role: `WarmupHelpersApi.senders()` → `GET /warmup-helpers/senders`:
  contact_count via `select(WarmupHelper.sender_instance_id, func.count()).group_by(...)`,
  `team_enabled = instance_id not in hs.enabled_sender_ids(db)`,
  `eligibility_overridden` via `sender_eligibility.override_active(cfg)`,
  `in_mesh_recovery` via `sender_eligibility.in_mesh_recovery_ids(db)`.
- Eligibility dialog: `WarmupHelpersApi.senderEligibility(id)` →
  `GET /warmup-helpers/sender-eligibility` → `sender_eligibility.check_sender_eligibility`
  + `sender_eligibility.has_valid_override`.
- Cold/recipient accounts (TC): `team-dashboard` reads `WarmupTeamEnrollment`
  (cold_instance_id, is_enabled, enrolled_at).

## SHARED single evaluator (confirmed — reuse directly, do NOT recompute)
- `warmup_warmth.warmth_for_account(db, account, now=None) -> dict`
  → `{score, level, components{age,incident_free,activity}, instance_id, name, eligible,
     reason, age_days, recent_incidents}`. Reuses V27 evaluators internally.
- `warmup_peer_eligibility`: `peer_age_days(account, enrollment, now)`,
  `_recent_incident_count(db, account_id, now)` (trailing 14d, disqualifying types),
  `evaluate_peer_eligibility(account, enrollment, count, now) -> (eligible, reason, msg)`.
  `MIN_PEER_AGE_DAYS = PEER_HISTORY_WINDOW_DAYS = 14`.
- `sender_eligibility.check_sender_eligibility(db, instance_id, now)
  -> (eligible, reason_slug, message_fa|None, age_days)`; reason ∈
  `{ok, in_mesh_recovery, too_young, recent_incident, not_found}`.
- `sender_eligibility.has_valid_override(db, instance_id) -> bool`.

## PART 2 plan (aggregation, pure reuse)
`GET /api/v1/accounts/overview`, one row per non-deleted account, assembled by calling:
- accounts source → connection state + `sent_today`/`received_today` (activity).
- `warmth_for_account` → warmth score/level, `days_connected(=age_days)`,
  `recent_incidents`(14d), components.
- `check_sender_eligibility` + `has_valid_override` → eligibility status + override.
- `health_breakdown` + `AccountIncident` query → health_score, last incident type/date,
  total incident count, `incident_count_7d`.
- mesh role logic (identical to warmup.mesh_dashboard) + `WarmupHelper` contact count +
  `hs.enabled_sender_ids` + `WarmupTeamEnrollment` → role (mesh peer / TC sender / cold / none).
No new scoring/eligibility/incident math is introduced.
