# V67.1 Phase 7.3 — Operational Authorization

## Scope

Controlled Stage A Shadow operationalization on ENV-A only.

## Environment

`claudegreenapi` Compose stack (PRODUCTION_LIKE).

## Cohort limit

Exactly **1** FleetAccount for Stage A. No automatic expansion.

## Flag sequencing

1. Flags remain false through enrollment, token, dry-run, persistence proofs  
2. Runtime `true` + Scheduler `false`  
3. Validate  
4. Scheduler `true` only after Runtime validation  
5. Observe ≥2 real 300s slots  
6. Official observation start = first successful scheduled snapshot  

## Monitoring cadence

Daily **06:00 UTC** (Tehran **09:30 IRST** unless rules change) + event-driven reviews.

## Stop authority

Project Owner; Backend/System Administrator. Follow `76` disable sequence.

## Retention

No auto-delete during window.

## Prohibited

Green API send, campaigns, Journey execution, FleetState mutation by Shadow, cutover, Canary, Human/Native Contacts, frontend, Autopilot, numeric dangerous threshold, fabricated engagement, claiming 14-day completion early.

## Observation-window integrity

14 full consecutive valid days required later. This phase may only start the window; it must not claim completion.
