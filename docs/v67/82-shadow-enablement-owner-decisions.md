# V67.1 Phase 7.3 — Shadow Enablement Owner Decisions (RATIFIED)

**Status:** All D-SE-01…D-SE-15 APPROVED by owner prompt for Phase 7.3.  
**Environment:** ENV-A `claudegreenapi` Compose stack.

## D-SE-01 — Candidate environment

**APPROVED:** ENV-A `claudegreenapi` Compose stack, classification `PRODUCTION_LIKE`.  
ENV-B not primary. Unrelated host stacks not involved.

## D-SE-02 — Migration

**APPROVED:** Accept `v67_07_fleet_shadow_snapshots` after read-only verification. Do not reapply if current.

## D-SE-03 — Temporary operator token

**APPROVED:** Provision strong Backend-only Shadow operator token on ENV-A.  
Never commit / print / log / store in DB or frontend. Backend role fixed. Client cannot self-assign role.

## D-SE-04 — Initial cohort

**APPROVED:** Stage A = **exactly 1** FleetAccount. Evidence-based selection. Dry-run before apply. No auto expansion.

## D-SE-05 — Manual run-once

**APPROVED:** Gate A dry-run (no persist) → Gate B one persisted snapshot only after Gate A passes.

## D-SE-06 — Runtime flag

**APPROVED conditionally:** `v67_shadow_runtime_enabled=true` only after all listed gates pass. Remains false until then.

## D-SE-07 — Scheduler flag

**APPROVED conditionally:** `v67_shadow_scheduler_enabled=true` only after Runtime validation and separate checkpoints. Not simultaneous with first Runtime enable.

## D-SE-08 — Scheduler frequency

**APPROVED:** Keep **300 seconds**. No faster. No catch-up.

## D-SE-09 — Observation start

**APPROVED conditionally:** Window starts at first successful **scheduled** Shadow snapshot after both flags enabled. No backdating.

## D-SE-10 — Emergency stop authority

**APPROVED:** Project Owner; Current authorized Backend/System Administrator.

## D-SE-11 — Monitoring cadence

**APPROVED:** Daily formal review **06:00 UTC**.  
Tehran equivalent at ratification: **09:30 IRST** (UTC+3:30). Recalculate if DST/rules change.

Immediate review on P0/P1, CRITICAL mismatch, runtime-unknown spike, stale critical sensors, Redis/DB/Celery failure, duplicates, unauthorized API pattern, performance impact.

## D-SE-12 — Data retention

**APPROVED:** No automatic deletion during observation. Keep all Phase 7 Shadow snapshots for 14 days. No cleanup worker.

## D-SE-13 — Dangerous mismatch threshold

**APPROVED:** Remain **UNRATIFIED**. Per-account dangerous classification remains visible. No numeric operational threshold.

## D-SE-14 — Frontend

**APPROVED:** Deferred. No frontend in Phase 7.3.

## D-SE-15 — Human/Native Contacts

**APPROVED:** Deferred until after valid Shadow milestones. Not implemented in Phase 7.3.
