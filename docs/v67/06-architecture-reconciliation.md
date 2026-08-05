# V67.1 Phase 0.5 — Architecture Reconciliation

**Mode:** Read + Design + Owner Decision Preparation  
**Branch:** `main` (local; ahead of origin by 12; no dedicated `v67` feature branch yet)  
**Constraint:** Documentation only. No code, DB, Green API, tests, commits, or pushes.

Cross-checked against: `docs/v67/03-conflict-map.md`, `04-reuse-plan.md`, `05-migration-plan.md`, `V67_1_AUTONOMOUS_FLEET_MANAGER_MASTER.md`.

---

## Part A — Conflict-by-conflict analysis

### H1 — Mesh AI own-account chat vs “no fake loops”

| Dimension | Detail |
|---|---|
| **Current** | `warmup_engine` + `warmup_ai` send AI messages between operator-owned instances via `WarmupMeshEdge`. Team Collaboration (`warmup_helper_*`) asks real humans. |
| **V67** | Fake/artificial loops forbidden; only consented real people; warmers may be `CONNECTED_WARMER_ACCOUNT` (system may send) or `HUMAN_PARTICIPANT` (task only). |
| **Technical impact** | Mesh is today’s primary automatic warm-up volume source. Disabling it without TC scale collapses inbound building. |
| **Migration complexity** | High. Dual-path Shadow required; enrollments mid-ramp must not break. |
| **Backward compatibility** | Existing enrollments must keep running until per-account cutover. |
| **Rollback** | Feature flag `MESH_AUTOCHAT=on\|shadow\|off`; off leaves TC+campaign untouched. |
| **Recommended** | **Hybrid WRAP:** Keep TC as primary V67 human path; wrap mesh as `LEGACY_MESH_CHANNEL` under AFM Shadow; **default OFF for new AFM journeys**; deprecate after canary; never delete until rollback-tested. Connected warm accounts send only to real consented contacts / cold under Policy — not AI peer loops as the long-term design. |
| **Alternative** | Amend V67.1 to allow own-account mesh as temporary warming substrate (owner product change). |
| **Owner decision?** | **YES** — D-H1 |

---

### H2 — Day 10 = WARMUP_READY vs current GRADUATED/MATURING

| Dimension | Detail |
|---|---|
| **Current** | General: days 5–10 RAMPING; 11–24 MATURING; ≥25 GRADUATED. Recovery: ≥12 GRADUATED. Campaign exclusion uses mesh GRADUATED / `days_active`. |
| **V67** | Day 10 → `WARMUP_READY` only; campaign via `GRADUATION_TRIAL` then `CAMPAIGN_READY`. |
| **Technical impact** | UI label `فارغ‌التحصیلی` and campaign eligibility would silently change. |
| **Migration complexity** | Medium–high (eligibility + Persian glossary + recovery path). |
| **Backward compat** | Grandfather currently GRADUATED accounts as `CAMPAIGN_READY` if incident-clean; new journeys follow V67 ladder. |
| **Rollback** | Policy flag `DAY10_SEMANTICS=legacy\|v67`. |
| **Recommended** | Adopt V67 ladder as canonical FleetState (see Part B §2 and `07-fleet-state-matrix.md`). Map legacy WarmupState → FleetState read-only until cutover. |
| **Alternative** | Keep day-25 campaign gate; treat day-10 as internal milestone only (rejects V67 non-negotiable). |
| **Owner decision?** | **YES** — D-H2 |

---

### H3 — Hard-coded 12→100 vs Policy DB

| Dimension | Detail |
|---|---|
| **Current** | `WarmupConfig.ramp_curve = [12,20,32,48,66,84,100]` |
| **V67** | Guidance only; live in Policy; hard-code forbidden. |
| **Technical impact** | Scheduler indexes curve by day; tests assert exact values. |
| **Migration complexity** | Low–medium. |
| **Backward compat** | Seed CONSERVATIVE policy with identical curve; `WarmupConfig` remains fallback when no policy_id. |
| **Rollback** | Delete policy rows; fallback to WarmupConfig. |
| **Recommended** | Policy DB is source of truth after Phase 2; seed from current curve; deprecate hard-code after Shadow compare. |
| **Alternative** | Keep code defaults forever; Policy only overrides (weaker compliance). |
| **Owner decision?** | **YES (light)** — D-H3 confirm seed = current curve |

---

### H4 — Triple state space

| Dimension | Detail |
|---|---|
| **Current** | `AccountStatus` + `WarmupState` + Green live state (+ onboarding steps). |
| **V67** | One Fleet journey SM for decisions. |
| **Technical impact** | Fourth write path without adapter reopens V57/V65 bugs. |
| **Migration complexity** | High conceptually; low if FleetState is projection only first. |
| **Backward compat** | Keep writing AccountStatus / WarmupState / live cache; FleetState derived + eventually authoritative for AFM actions. |
| **Rollback** | Ignore `fleet_accounts`; legacy paths unchanged. |
| **Recommended** | **Canonical FleetState on `fleet_accounts`** (not a column fight on `accounts.status`). Adapter matrix is single derivation function. AFM actions consult FleetState + `send_gate` (never bypass). |
| **Alternative** | Replace AccountStatus enum (dangerous; reject for Phase 1–4). |
| **Owner decision?** | **YES (confirm separate table)** — D-H4 |

---

### H5 — Alembic vs startup DDL

| Dimension | Detail |
|---|---|
| **Current** | `create_all` + `main.py` IF NOT EXISTS; empty Alembic versions. |
| **V67** | Up/down migrations required. |
| **Technical impact** | Phase 2 acceptance blocked without tooling. |
| **Migration complexity** | Medium (baseline stamp against live schema). |
| **Backward compat** | Keep IF NOT EXISTS until stamp verified on staging. |
| **Rollback** | Downgrade drops only new `fleet_*` objects. |
| **Recommended** | Introduce Alembic in Phase 2 start; baseline stamp; freeze new main.py DDL; hybrid safety net ≤1 release. |
| **Alternative** | Waive down-scripts for Phase 2 (rejects master acceptance). |
| **Owner decision?** | **YES** — D-H5 |

---

### C1 — Circuit breaker 24h vs mesh 48h

| Dimension | Detail |
|---|---|
| **Current** | Mesh killswitch: ≥2 distinct card/block in **48h** → pause whole mesh. |
| **V67** | Fleet stop if **2 Suspend in 24h**; owner reset only. |
| **Technical impact** | Dual breakers can double-pause or disagree. |
| **Complexity** | Medium. |
| **Compat** | Keep mesh 48h during Shadow; add fleet 24h Suspend breaker as additive AFM layer. |
| **Rollback** | Disable fleet breaker flag. |
| **Recommended** | **Coexistence:** Fleet breaker owns campaign+AFM outbound; mesh breaker owns mesh tick only; document precedence: Fleet STOP ⊇ Mesh pause. Unify windows to 24h only after canary. |
| **Alternative** | Immediately change mesh to 24h (riskier). |
| **Owner decision?** | **YES** — D-C1 |

---

### C2 — Peer ratio 1:3

| Dimension | Detail |
|---|---|
| **Current** | `peers_per_new_number_min=3`, `max=6`. |
| **V67** | Fixed 1:3 not confirmed. |
| **Recommended** | Policy fields `peers_min`/`peers_max`; defaults 3–6; never document as Green API fact. |
| **Owner decision?** | No (soft default OK) |

---

### C3 — Campaign lock fail-open

| Dimension | Detail |
|---|---|
| **Current** | Redis down → run without lock. |
| **V67** | Atomic claim; dual worker = one action. |
| **Recommended** | Phase 5: fail-closed for AFM action claims; campaign lock configurable `LOCK_FAIL=open\|closed` default **closed** for new AFM, **open** legacy until canary. |
| **Owner decision?** | **YES** — D-C3 |

---

### C4 — Native contact = OS address book

| Dimension | Detail |
|---|---|
| **Current** | Green API `addContact` / mesh handshake flags. |
| **V67** | Phone primary address book required. |
| **Recommended** | New field `native_contact_verified` (manual/operator attestation or future device signal). Never auto-set from API addContact. Compliance Score fails closed if false when Policy requires it. |
| **Owner decision?** | **YES** — D-C4 attestation process |

---

### C5 — Typing autoTyping vs SendTyping

| Dimension | Detail |
|---|---|
| **Current** | Warming settings `autoTyping:2`; campaigns optional `typing_simulation`. |
| **V67** | Prefer autoTyping; SendTyping fallback. |
| **Recommended** | AFM always ensures instance autoTyping via adapter; SendTyping only fallback; do not globally enable campaign typing_simulation. |
| **Owner decision?** | No |

---

### C6 — Maintenance idle numbers

| Dimension | Detail |
|---|---|
| **Current** | keepwarm 10d; erosion 14d; autologout 30d. |
| **V67** | Few real daily messages; no official count. |
| **Recommended** | Policy knobs; seed from current constants; MaintenanceManager uses evidence not magic. |
| **Owner decision?** | No |

---

### C7 — AI authority

| Dimension | Detail |
|---|---|
| **Current** | Gates rule-based; AI chooses content / can influence tick plans. |
| **V67** | AI suggests; Rule Engine decides; AI cannot raise caps. |
| **Recommended** | ActionPlanner/CapacityPlanner ignore AI for caps; AI only fills message templates inside already-approved slots. |
| **Owner decision?** | No |

---

### C8 — Recovery GRADUATED ~day 12

| Dimension | Detail |
|---|---|
| **Current** | Recovery → GRADUATED at day_index ≥ 12. |
| **V67** | Still need trial before CAMPAIGN_READY; incidents → REWARM_REQUIRED. |
| **Recommended** | Map recovery “GRADUATED” → Fleet `WARMUP_READY`; require `GRADUATION_TRIAL` before campaign. UI: stop calling it campaign-ready. |
| **Owner decision?** | Bundled with D-H2 |

---

### C9 — Branch strategy

| Dimension | Detail |
|---|---|
| **Current** | Work on `main`, ahead 12, redesign branch exists. |
| **Recommended** | Create `v67/phase0.5-docs` or `v67/fleet` before Phase 1 code. |
| **Owner decision?** | **YES** — D-C9 |

---

## Part B — Final reconciliation designs

### B1. Mesh warm-up + Team Collaboration

**Decision shape: Hybrid WRAP (recommended).**

| Layer | Role |
|---|---|
| **Team Collaboration** | KEEP + EXTEND → V67 Human Participants + CONNECTED_WARMER sends. Primary long-term inbound/bidirectional evidence. |
| **Mesh autochat** | WRAP as `LegacyMeshAdapter` behind AFM. Shadow-compare only for new Autopilot accounts unless owner chooses D-H1 alternative. Existing enrollments: WRAP until cutover. |
| **Group warm-up** | KEEP additive (optional inbound diversity). |
| **Replace?** | Not in Phase 1–8. REPLACE mesh autochat only after Shadow+Canary proves TC+warmer path can sustain flow. |
| **Remove?** | Only after rollback-tested release (master §20). |

Exact wiring:

```
JourneyOrchestrator
  ├─ channel=HUMAN_TASK     → warmup_helper_engine (WRAP)
  ├─ channel=CONNECTED_WARMER → send via GreenApiAdapter + send_gate (existing TC/mesh send helpers)
  └─ channel=LEGACY_MESH    → warmup_engine (WRAP; flag-gated)
```

---

### B2. Warm-up lifecycle (final)

Canonical happy path (V67):

```
NEW → PRECHECK → QR_WAITING → READY_TO_LINK → AUTHORIZED_QUIET
  → INBOUND_BUILDING → BIDIRECTIONAL_BUILDING → CONTROLLED_RAMP
  → WARMUP_READY → GRADUATION_TRIAL → CAMPAIGN_READY → MATURE → MAINTENANCE
```

**Day semantics (recommended freeze):**

| Day index (policy) | FleetState target | Campaign? |
|---|---|---|
| 1 | AUTHORIZED_QUIET / still quiet | No |
| 2–N inbound | INBOUND_BUILDING | No |
| Bidirectional evidence | BIDIRECTIONAL_BUILDING | No |
| Ramp window (policy curve) | CONTROLLED_RAMP | No |
| End of base ramp ≈ day 10 CONSERVATIVE | **WARMUP_READY** | Trial only |
| Trial pass | GRADUATION_TRIAL → CAMPAIGN_READY | Capacity-limited |
| 25–30 healthy | MATURE | Policy capacity |
| Ongoing | MAINTENANCE | Policy |

**Legacy WarmupState mapping (read adapter):**

| WarmupState | FleetState (approx) |
|---|---|
| ENROLLED / COOLDOWN | AUTHORIZED_QUIET or QR-adjacent quiet |
| RECEIVING | INBOUND_BUILDING |
| REPLYING | BIDIRECTIONAL_BUILDING |
| RAMPING | CONTROLLED_RAMP |
| MATURING | WARMUP_READY or late CONTROLLED_RAMP (not CAMPAIGN_READY) |
| GRADUATED (general ≥25) | CAMPAIGN_READY / MATURE (grandfather) |
| GRADUATED (recovery ≥12) | WARMUP_READY (not campaign) |
| PAUSED | PAUSED |
| YELLOWCARD | AT_RISK or PAUSED |
| BLOCKED_RESET | REWARM_REQUIRED |

Full matrix: `07-fleet-state-matrix.md`.

---

### B3. Daily flow → Policy DB

1. Phase 2: `fleet_policies` with JSON `ramp_curve`, `day10_state=WARMUP_READY`, windows, peers_min/max, breaker thresholds.  
2. Seed CONSERVATIVE = current `WarmupConfig` values (bit-identical).  
3. `PolicyEngine.get_effective(account)` → snapshot onto journey.  
4. `warmup_scheduler` WRAP: if policy snapshot present use it; else WarmupConfig.  
5. After Shadow: remove hard-code from *new* code paths; keep WarmupConfig as dead fallback one release.  
6. `total_daily_flow` metric = inbound + outbound (from counters + later unique chats).

---

### B4. Canonical status model

```
                    ┌─────────────────────┐
   Webhooks/Poll ──►│ Green live state    │  (sensor)
                    └─────────┬───────────┘
                              │
   Account row ───────────────┼──► AccountStatus (connectivity/ops)
                              │
   WarmupEnrollment ──────────┼──► WarmupState (legacy journey)
                              │
                              ▼
                    ┌─────────────────────┐
   Classifier ─────►│ FleetState          │  ★ single AFM decision truth
   + Policy/Risk    │ (fleet_accounts)    │
                    └─────────┬───────────┘
                              │
                              ▼
                    Journey / Capacity / Campaign allow-deny
                              │
                              ▼
                    send_gate (always) → Green API
```

Rules:

- AFM **never** invents a parallel send bypass.  
- `AccountStatus.suspended|banned|disconnected` force FleetState danger states.  
- Live `yellowCard|blocked|suspended|notAuthorized` force immediate Fleet danger + gate block.  
- WarmupState is **legacy mirror** until mesh cutover; not authoritative for Autopilot accounts.

---

### B5. Database migration strategy (final design)

1. **Phase 1:** zero DDL (P0 code only; incidents/activity fields if needed via careful additive later — prefer Phase 2).  
2. **Phase 2 start:** Alembic enabled; `v67_01_baseline_stamp` (no-op upgrade, stamp current).  
3. Additive `fleet_*` revisions with down scripts.  
4. Keep `main.py` IF NOT EXISTS as safety net one release; then freeze.  
5. `fleet_accounts` separate from `accounts.status`.  
6. Helpers: EXTEND columns in place first; optional `human_participants` view/table later.  
7. Rollback = downgrade fleet revisions; never drop warmup_*.

---

## Part C — Conflicts resolved by design (pending owner sign-off)

| ID | Resolved by recommended design? | Still needs owner? |
|---|---|---|
| H1 | Hybrid WRAP proposed | YES |
| H2 | V67 ladder + mapping | YES |
| H3 | Policy seed path | Light YES |
| H4 | fleet_accounts canonical | Confirm YES |
| H5 | Alembic+stamp | YES |
| C1 | Coexistence | YES |
| C2 | Policy peers | No |
| C3 | Fail-closed AFM | YES |
| C4 | Attestation field | YES |
| C5–C7 | Defaults | No |
| C8 | With H2 | With H2 |
| C9 | Feature branch | YES |

See `09-owner-decisions.md` and `10-phase1-readiness.md`.
