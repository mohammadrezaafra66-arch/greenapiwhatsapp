# V67.1 Phase 7 — Owner Decisions (unresolved)

All items require explicit owner answer before Phase 7 readiness can be YES.  
Format: yes/no or multiple choice. Default for implementation until answered: **fail closed / do not start**.

---

### D-P7-01 — Execution Phase 7 identity
Confirm execution Phase 7 is **Shadow Runtime only** (not Master `فاز ۷` Human/Native Contacts)?  
[ ] YES — Shadow only  
[ ] NO — explain alternate numbering

### D-P7-02 — Live Journey
Is Live Journey forbidden for entire Phase 7?  
[ ] YES — forbidden  
[ ] NO — allowed under conditions: ___

### D-P7-03 — send_gate authority
Does `send_gate` remain the sole live send authority with zero FleetState cutover in Phase 7?  
[ ] YES  
[ ] NO

### D-P7-04 — Eligibility operational effect
Does Eligibility remain recommendation/compare-only (never grants send)?  
[ ] YES  
[ ] NO

### D-P7-05 — cutover flag
Must `fleet_accounts.cutover` remain false for all accounts during Phase 7?  
[ ] YES  
[ ] NO

### D-P7-06 — Canary
Is Canary deferred to Phase 8+ (not Phase 7)?  
[ ] YES — deferred  
[ ] NO — include in Phase 7 (requires redesign)

### D-P7-07 — Campaign bridge
Is real campaign execution bridge forbidden in Phase 7?  
[ ] YES — forbidden  
[ ] NO

### D-P7-08 — Shadow scheduler
Authorize Celery periodic shadow snapshot task with default `v67_shadow_runtime_enabled=false`?  
[ ] YES  
[ ] NO — CLI/API only

### D-P7-09 — Persistence table
Prefer new `fleet_shadow_snapshots` when `fleet_plan_snapshots` lacks account/mismatch indexes?  
[ ] YES — additive reversible table  
[ ] NO — extend plan snapshots only

### D-P7-10 — Observation window
Minimum Shadow observation window before Canary discussion?  
[ ] 7 days  
[ ] 14 days  
[ ] 30 days  
[ ] Other: ___

### D-P7-11 — Dangerous mismatch threshold
What CRITICAL mismatch rate (policy) pauses Shadow scheduling?  
[ ] Owner supplies number  
[ ] Defer until Phase 7 design workshop

### D-P7-12 — High-volume readiness
Confirm High Volume requires **only** `READY_FOR_MATURE` (Phase 6.1 fail-closed)?  
[ ] YES — keep  
[ ] NO — also allow `READY_FOR_CAMPAIGN`

### D-P7-13 — Journey COMPLETED
Should Journey `COMPLETED` be allowed for eligibility simulation, or remain fail-closed?  
[ ] Allow COMPLETED  
[ ] Fail closed (current Phase 6.1)

### D-P7-14 — Missing Journey
Keep missing Journey as fail-closed for eligibility?  
[ ] YES  
[ ] NO — allow with reason

### D-P7-15 — Human/Native Contacts (Master فاز ۷)
When should Master Human/Native Contacts execute relative to Shadow?  
[ ] After Shadow, before Canary  
[ ] After Canary  
[ ] Parallel track under different execution ID  
[ ] Other: ___

### D-P7-16 — Operator API auth
Fleet Shadow APIs currently inherit open `/api/v1` (no RBAC). Require privileged role for `run-once` before Phase 7 ship?  
[ ] YES — add auth  
[ ] NO — document as known gap (ops network trust)

---

**None of the above are ratified.** Phase 7 readiness remains **NO**.
