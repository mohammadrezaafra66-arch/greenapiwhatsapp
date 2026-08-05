# V67.1 — Shadow / Diagnostics Gap Inventory (READ-ONLY)

**Mode:** Inventory only. No implementation in this document’s closure.  
**Authority:** Owner Decision 2 in `109-phase8-identity-and-phase7-gate-decision.md`.  
**Rule:** Do not rebuild Phase 7 observational substrate. Do not title these items Phase 8.

Classification columns:

- **Status:** Existing | Partial | Missing  
- **Duplicate risk:** High | Medium | Low  
- **Correct future phase / bucket:** one of Phase 7 observation/audit hardening; Shared diagnostic infrastructure; Future Cutover preparation; Deferred technical debt; Master Dashboard (فاز ۱۱); or post-acceptance Shadow hardening (not Phase 8 Graduation)  
- **Blocking:** whether it blocks Phase 7 Fully Accepted / Session 2 validity now  

---

## Decision Explainer

**Status:** Partial.  
Eligibility and Shadow already emit `reason_codes`, comparison details, and eligibility `next_recommendation`. Master dependency graph names DecisionExplainer as a persist step; no dedicated narrative Explainer service exists.  
**Duplicate risk:** High if a parallel “Phase 8 Explainer” reimplements Shadow/eligibility codes.  
**Correct future phase:** Shared diagnostic infrastructure (or Master Dashboard reason visibility). Not Phase 8 Graduation/Maintenance.  
**Blocking now:** Non-blocking for Session 2 day validity.

## Replay

**Status:** Missing as product. Run-once re-evaluates live sensors; it does not freeze and re-apply stored snapshot inputs.  
**Duplicate risk:** Medium vs `POST /fleet/shadow/run-once` and CLI `fleet_shadow_run`.  
**Correct future phase:** Phase 7 observation/audit hardening or Shared diagnostic infrastructure after Phase 7 Fully Accepted. Not Phase 8 Graduation.  
**Blocking now:** Non-blocking (must not replace real observation time).

## Diff

**Status:** Missing as dedicated two-snapshot diff API. Operators can manually compare JSON via snapshot GET/history.  
**Duplicate risk:** Medium vs `/fleet/shadow/snapshots/{id}` and history list.  
**Correct future phase:** Shared diagnostic infrastructure. Not Phase 8 Graduation.  
**Blocking now:** Non-blocking.

## Timeline

**Status:** Partial. Account history list exists (`GET /fleet/shadow/accounts/{id}/history`); no first-class timeline product.  
**Duplicate risk:** Medium.  
**Correct future phase:** Shared diagnostic infrastructure / Master Dashboard (فاز ۱۱). Not Phase 8 Graduation.  
**Blocking now:** Non-blocking.

## Trace IDs

**Status:** Partial. `run_id` and `idempotency_key` exist on snapshots; no distributed bridge_trace model.  
**Duplicate risk:** High if a second ID scheme is invented beside `run_id`.  
**Correct future phase:** Phase 7 observation/audit hardening or Shared diagnostic infrastructure.  
**Blocking now:** Non-blocking.

## Failure catalog

**Status:** Partial / Missing as versioned catalog. Codes exist ad hoc in comparison and eligibility; no single operator catalog document/module.  
**Duplicate risk:** High if catalog diverges from live `reason_codes`.  
**Correct future phase:** Shared diagnostic infrastructure.  
**Blocking now:** Non-blocking for day counting; helpful for daily review quality.

## Integrity validator (Bridge integrity)

**Status:** Missing as named Bridge integrity layer. Implicit checks exist (cutover refuse, simulation flags, schema CHECKs).  
**Duplicate risk:** Medium vs Shadow status endpoint and migration guards.  
**Correct future phase:** Phase 7 observation/audit hardening (data-integrity / continuity). Not Phase 8 Graduation. Not “Bridge phase”.  
**Blocking now:** Non-blocking if ENV-A cohort/snapshots remain consistent; becomes blocking if wipe/regression reappears.

## Runtime consistency validator

**Status:** Partial. Comparison engine + freshness + cutover refuse; no dedicated consistency report module.  
**Duplicate risk:** Medium vs `ShadowComparisonEngine` and `/drift`.  
**Correct future phase:** Phase 7 observation/audit hardening.  
**Blocking now:** Partially relevant — open `RUNTIME_UNKNOWN` / `live_state_missing` is an observation quality issue, not a license to start Phase 8.

## Diagnostic CLI

**Status:** Partial. `fleet_shadow_run`, `fleet_shadow_daily_report`, fleet seed/simulate scripts exist; no dedicated diagnostic/replay CLI product.  
**Duplicate risk:** Medium.  
**Correct future phase:** Shared diagnostic infrastructure.  
**Blocking now:** Non-blocking (daily report CLI sufficient for Stage A review).

## Read-only health API

**Status:** Partial. `/fleet/shadow/status`, `/summary`, `/drift` plus generic app health; no fleet-wide health dashboard API product.  
**Duplicate risk:** High if a parallel “Bridge Health” API clones Shadow status.  
**Correct future phase:** Shared diagnostic infrastructure / Master Dashboard (فاز ۱۱).  
**Blocking now:** Non-blocking.

## Policy-version tracking

**Status:** Partial. `fleet_policies.version` and snapshot `policy_version` plus mismatch class `POLICY_VERSION_MISMATCH`; no version timeline/diff UX.  
**Duplicate risk:** Medium.  
**Correct future phase:** Shared diagnostic infrastructure; Future Cutover preparation when policies become operationally binding. Not Phase 8 Graduation pools themselves.  
**Blocking now:** Non-blocking (threshold remains UNRATIFIED).

---

## Summary rule

None of the above may be implemented as **Phase 8**. Phase 8 remains Master **Graduation / Maintenance** and stays **NOT STARTED** until Phase 7 Fully Accepted and a later explicit owner command. During Session 2, only narrow observation-preserving fixes are allowed (`109` Decision 4).
