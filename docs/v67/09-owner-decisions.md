# V67.1 Phase 0.5 — Owner Decision Sheet

Sign each Decision ID before Phase 1 implementation.  
**Recommended** = architecture team default if owner accepts without change.  
**Default** = provisional value used in Shadow if owner delays (still requires eventual sign-off for Hard Stops).

**Phase 1 ratification:** Owner accepted ALL Recommended answers exactly (2026-08-05).  
Implementation notes below copy Recommended text verbatim; Status lines are additive only.

---

## Hard stops

### D-H1 — Mesh autochat future

| Field | Content |
|---|---|
| **Question** | Keep AI own-account mesh loops as long-term warm-up, or Hybrid WRAP (TC + connected warmers primary; mesh flag-gated legacy)? |
| **Recommended** | Hybrid WRAP; mesh default OFF for new Autopilot journeys; existing enrollments continue until cutover; deprecate after canary |
| **Risk** | Medium — inbound volume may drop if TC not scaled |
| **Impact** | Journey design, ethics compliance, Celery ticks |
| **Default** | Hybrid WRAP (recommended) |
| **Owner decision required?** | **YES** |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Hybrid WRAP; mesh default OFF for new Autopilot journeys; existing enrollments continue until cutover; deprecate after canary |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

### D-H2 — Day-10 / graduation vocabulary

| Field | Content |
|---|---|
| **Question** | Confirm Day 10 = `WARMUP_READY` only; campaign only after `GRADUATION_TRIAL`; recovery “GRADUATED” maps to `WARMUP_READY`? |
| **Recommended** | Yes — adopt V67 ladder; grandfather general mesh GRADUATED (≥25) as CAMPAIGN_READY if clean |
| **Risk** | High if UI/ops still treat فارغ‌التحصیلی as full campaign |
| **Impact** | Eligibility, Persian copy, recovery Path B |
| **Default** | V67 ladder |
| **Owner decision required?** | **YES** |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Yes — adopt V67 ladder; grandfather general mesh GRADUATED (≥25) as CAMPAIGN_READY if clean |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

### D-H3 — Policy seed curve

| Field | Content |
|---|---|
| **Question** | Seed CONSERVATIVE `ramp_curve` exactly as `[12,20,32,48,66,84,100]`? |
| **Recommended** | Yes — bit-identical to current WarmupConfig |
| **Risk** | Low |
| **Impact** | PolicyEngine Phase 2 |
| **Default** | Yes |
| **Owner decision required?** | Light YES |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Yes — bit-identical to current WarmupConfig |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

### D-H4 — FleetState storage

| Field | Content |
|---|---|
| **Question** | Store canonical FleetState on separate `fleet_accounts` table (recommended) vs column on `accounts`? |
| **Recommended** | Separate `fleet_accounts` |
| **Risk** | Low–medium (join cost) |
| **Impact** | Phase 2 schema |
| **Default** | Separate table |
| **Owner decision required?** | YES (confirm) |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Separate `fleet_accounts` |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

### D-H5 — Alembic

| Field | Content |
|---|---|
| **Question** | Introduce Alembic with baseline stamp + down scripts in Phase 2, keeping main.py IF NOT EXISTS one release? |
| **Recommended** | Yes |
| **Risk** | Medium (stamp accuracy) |
| **Impact** | All future DDL |
| **Default** | Alembic yes |
| **Owner decision required?** | **YES** |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Yes |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

---

## Soft / borderline

### D-C1 — Breaker windows

| Field | Content |
|---|---|
| **Question** | Coexist fleet 24h Suspend breaker with mesh 48h breaker until canary, then unify? |
| **Recommended** | Coexist then unify to 24h |
| **Risk** | Dual pause confusion |
| **Impact** | Phase 1 breaker + killswitch |
| **Default** | Coexist |
| **Owner decision required?** | YES |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Coexist then unify to 24h |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

### D-C3 — Redis lock fail mode

| Field | Content |
|---|---|
| **Question** | AFM action claims fail-closed when Redis down? Legacy campaign lock? |
| **Recommended** | AFM fail-closed; legacy campaign fail-open until canary then closed |
| **Risk** | Availability vs double-send |
| **Impact** | Phase 5 |
| **Default** | As recommended |
| **Owner decision required?** | YES |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | AFM fail-closed; legacy campaign fail-open until canary then closed |
| **Phase 1 campaign lock note** | Phase 1 mission Acceptance requires campaign Redis lock fail-closed now. That executes the “then closed” clause of this Recommended answer for the campaign lock in Phase 1. AFM action-claim locks remain Phase 5 (fail-closed). Recommended text above is preserved unchanged. |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

### D-C4 — Native contact attestation

| Field | Content |
|---|---|
| **Question** | How is `native_contact_verified` set — operator checkbox, bulk import attestation, or block until device signal exists? |
| **Recommended** | Operator attestation required for CONSERVATIVE; never auto from Green API addContact |
| **Risk** | Process burden |
| **Impact** | Compliance Score Phase 7 |
| **Default** | Operator attestation |
| **Owner decision required?** | YES |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Operator attestation required for CONSERVATIVE; never auto from Green API addContact |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

### D-C9 — Git branch

| Field | Content |
|---|---|
| **Question** | Create dedicated `v67/fleet` (or similar) feature branch before Phase 1 code? |
| **Recommended** | Yes — do not pile Phase 1 onto unpushed main drift blindly |
| **Risk** | Low |
| **Impact** | Process |
| **Default** | Yes |
| **Owner decision required?** | YES |
| **Status** | APPROVED |
| **Owner decision** | ACCEPT RECOMMENDED |
| **Approved at** | 2026-08-05T16:32:00+03:30 |
| **Implementation authority** | Phase 1+ |
| **Implementation notes (exact Recommended)** | Yes — do not pile Phase 1 onto unpushed main drift blindly |
| **Branch created** | `feature/v67-autonomous-fleet-manager` (fulfills “or similar”) |
| **Ratification mark** | APPROVED — OWNER ACCEPTED RECOMMENDED |

---

## No owner meeting required (locked defaults)

| ID | Default |
|---|---|
| C2 peers | Policy `peers_min=3`, `peers_max=6`; not advertised as Green fact |
| C5 typing | Prefer instance `autoTyping`; SendTyping fallback; no global typing_simulation |
| C6 idle | Policy-seed from keepwarm 10 / erosion 14 / logout 30 |
| C7 AI | AI never raises caps; Rule Engine final |

---

## Service classification (TASK 6)

| Service / module | Class | Notes |
|---|---|---|
| `green_api.GreenAPIClient` | **KEEP** + WRAP via GreenApiAdapter | No second client |
| `api/v1/webhook.py` | **KEEP** + WRAP events | Extend incident paths |
| `send_gate` | **KEEP** | Always final veto |
| `governors` | **KEEP** | Under Capacity |
| `volume_guard` | **KEEP** | Risk/capacity input |
| `redis_rate_limiter` | **KEEP** | Hard ceiling |
| `account_selection` / FanOut | **KEEP** | Campaign |
| `incident_handler` | **EXTEND** | Block/logout incidents |
| `state_monitor` | **KEEP** | suspendedUntil |
| `price_service` | **KEEP** + WRAP | ≤60s contract |
| `optout` / blacklist | **KEEP** | STOP |
| `campaign_runner` | **KEEP** + WRAP planner | No fork |
| `group_campaign_runner` | **KEEP** | |
| `warmup_engine` / mesh | **WRAP** → later **DEPRECATE** | Flag-gated legacy |
| `warmup_state` / scheduler | **WRAP** | Read map to FleetState |
| `warmup_killswitch` | **WRAP** + coexist breaker | |
| `warmup_recovery_*` | **WRAP** → RecoveryManager backend | |
| `warmup_helper_*` / TC | **KEEP** + **EXTEND** | Humans |
| `warmup_peer_eligibility` / warmth | **KEEP** | Trust inputs |
| `warmup_group_*` | **KEEP** | Optional |
| `warmup_auto` / legacy phrase warmup | **DEPRECATE** after cutover | |
| `onboarding_service` | **KEEP** + WRAP | QR_WAITING |
| `account_health` / `quality_score` | **KEEP** | Score inputs |
| `send_metrics` | **KEEP** | |
| `typing_sim` | **KEEP** | Fallback path |
| `peer_pacer` | **EXTEND** | Move critical pacing to Redis under AFM |
| `celery_app` / tasks | **EXTEND** | Add AFM tick |
| Frontend Warmup/TC/Campaigns/Protection | **KEEP** | Compose Fleet UI later |
| Parallel AFM send engine | **REMOVE** — never build | |
| Immediate delete of mesh | **FORBIDDEN** | Only after cutover+rollback test |

---

## Sign-off block

| Decision ID | Owner choice | Date | Initials |
|---|---|---|---|
| D-H1 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-H2 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-H3 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-H4 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-H5 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-C1 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-C3 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-C4 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
| D-C9 | ACCEPT RECOMMENDED | 2026-08-05 | OWNER |
