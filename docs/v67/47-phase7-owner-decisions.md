# V67.1 Phase 7 — Owner Decisions (RATIFIED)

**Ratified at:** 2026-08-05  
**Branch:** `feature/v67-autonomous-fleet-manager`  
**Status:** All D-P7-01 … D-P7-16 = **APPROVED**  
**Implementation:** NOT started — wait for explicit `Execute V67.1 Phase 7`

---

### D-P7-01 — PHASE 7 IDENTITY

**APPROVED**

Phase 7 execution scope is **Shadow Runtime only**.

Phase 7 must NOT implement the Master Human/Native Contacts scope inside the same execution phase.

Human/Native Contacts will be handled as a separate controlled phase after Shadow and before Canary.

---

### D-P7-02 — LIVE JOURNEY

**APPROVED**

Live Journey is forbidden for the entire Phase 7.

Allowed: reading Journey data; evaluating Journey recommendations; comparing expected and legacy behavior; recording Shadow diagnostics.

Forbidden: executing Journey actions; changing Journey state from Shadow; scheduling live Journey actions; triggering Green API operations.

---

### D-P7-03 — SEND_GATE AUTHORITY

**APPROVED**

`send_gate` remains the sole live-send authority during Phase 7.

Phase 7 must not: grant send permission; deny live sends through FleetState; import Shadow decisions into send_gate; replace existing send eligibility; alter current send behavior.

Zero FleetState cutover is authorized.

---

### D-P7-04 — ELIGIBILITY EFFECT

**APPROVED**

Campaign Eligibility remains recommendation-only, comparison-only, Shadow-only.

Eligibility decisions must never grant live send permission in Phase 7.

---

### D-P7-05 — CUTOVER FLAG

**APPROVED**

`fleet_accounts.cutover` must remain `false` for every account during Phase 7.

Phase 7 must not expose any API, CLI, task, migration, or service capable of setting it to `true`.

Tests must assert this prohibition.

---

### D-P7-06 — CANARY

**APPROVED**

Canary is deferred. No Canary implementation in Phase 7.

Canary may be discussed only after: Phase 7 Shadow completion; minimum observation window completion; mismatch analysis; owner review; explicit next-phase authorization.

---

### D-P7-07 — REAL CAMPAIGN BRIDGE

**APPROVED**

Real campaign execution bridge is forbidden in Phase 7.

Shadow may compare eligibility/planner recommendations, existing campaign behavior, and projected outcomes.

Shadow must not create/start a real campaign, enqueue recipients, dispatch campaign jobs, reserve live capacity, or execute sends.

---

### D-P7-08 — SHADOW SCHEDULER

**APPROVED**

Authorize a Celery periodic Shadow snapshot task only under all of:

- feature flag default `v67_shadow_runtime_enabled=false`
- task performs read/evaluate/compare/persist only
- no Green API call / send / live Journey / campaign / FleetState / cutover / send_gate mutation
- fail closed on DB/Redis/Policy/State uncertainty
- idempotent; per-account locking; safe retry; auditable output

CLI/API run-once remains available for controlled testing.

The feature flag must remain disabled after Phase 7 implementation. Do not enable the periodic task in any live environment during Phase 7 implementation or tests.

---

### D-P7-09 — SHADOW PERSISTENCE

**APPROVED**

Create dedicated additive reversible table: `fleet_shadow_snapshots`.

Do not overload `fleet_plan_snapshots` for continuous Shadow history.

Migration must be additive, reversible, safe, tested upgrade/downgrade/re-upgrade, free of destructive changes.

---

### D-P7-10 — OBSERVATION WINDOW

**APPROVED**

Minimum Shadow observation window before Canary discussion: **14 full consecutive days**.

Window starts only when: Shadow flag explicitly enabled in an approved environment; scheduler health verified; snapshots produced successfully; no unresolved P0/P1 Shadow defect.

Implementation and automated tests do not count toward the observation window.

---

### D-P7-11 — DANGEROUS MISMATCH THRESHOLD

**APPROVED**

Do not invent or activate a production percentage threshold during Phase 7 implementation.

Phase 7 must: store threshold in versioned Policy; provide safe disabled/unratified state; calculate and display mismatch rates; support simulation of candidate thresholds; fail closed when threshold missing; never trigger live operational changes.

Before enabling Shadow scheduling in an approved environment, conduct a design review using real Shadow baseline data and obtain a **separate** owner decision for the numeric threshold.

Until then: `dangerous_mismatch_threshold_status=UNRATIFIED`. No permissive fallback.

---

### D-P7-12 — HIGH-VOLUME READINESS

**APPROVED**

Keep Phase 6.1 fail-closed rule: High Volume requires `READY_FOR_MATURE` only.

Do not allow `READY_FOR_CAMPAIGN` to unlock High Volume.

---

### D-P7-13 — JOURNEY COMPLETED

**APPROVED**

Keep Journey `COMPLETED` fail-closed for campaign eligibility.

A completed Journey must not automatically imply current operational readiness.

---

### D-P7-14 — MISSING JOURNEY

**APPROVED**

Keep missing Journey fail-closed for eligibility.

Missing Journey may be reported in Shadow diagnostics but must not grant any eligibility tier.

---

### D-P7-15 — HUMAN/NATIVE CONTACTS

**APPROVED**

Execute Master Human/Native Contacts as a separate controlled phase: **after Shadow implementation, before Canary**.

Required sequence:

1. Phase 7 — Shadow Runtime  
2. Human/Native Contacts phase  
3. Shadow validation including contact/compliance evidence  
4. Canary readiness  
5. Canary only after explicit owner authorization  

Do not implement Human/Native Contacts inside Phase 7.  
Do not start Canary before Human/Native Contacts requirements are implemented and validated.

---

### D-P7-16 — OPERATOR API AUTH

**APPROVED**

Privileged authentication and RBAC are mandatory for every Shadow operation capable of: run-once evaluation; persistence; scheduler control; policy inspection containing operational configuration; fleet-wide diagnostics; export; retention/deletion; feature-flag control.

Read-only operator visibility must also require an authenticated authorized role.

Do not rely only on trusted internal network access. Unauthenticated Shadow APIs are forbidden.

---

## Security and scope freeze (still forbidden in Phase 7)

- live sending / Green API mutation or send calls  
- live Journey execution / campaign execution / real campaign bridge  
- send_gate integration / FleetState-based live send decision  
- cutover=true / Canary / Autopilot / legacy removal / production activation  
- Human/Native Contacts implementation  
- numeric dangerous-mismatch activation without a later owner decision  

---

## Ratification mark

**ALL D-P7-01 … D-P7-16 APPROVED — OWNER ACCEPTED EXPLICIT TEXT (2026-08-05)**
