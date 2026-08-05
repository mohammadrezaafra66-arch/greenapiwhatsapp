# V67.1 Phase 7.2 — Shadow Enablement Owner Decisions

**No decision below is approved.** Owner must answer explicitly.

## D-SE-01 — Candidate environment

- [ ] Approve exact named environment: `claudegreenapi` Compose stack (ENV-A)
- [ ] Reject and require a new isolated staging environment
- [ ] Select another named environment: ________

## D-SE-02 — Migration

- [ ] Confirm `v67_07` on ENV-A is accepted as applied
- [ ] Authorize apply on a different environment: ________
- [ ] Do not authorize

## D-SE-03 — Temporary operator token

- [ ] Authorize secure Backend token provisioning on approved env
- [ ] Do not authorize

## D-SE-04 — Initial cohort

- [ ] Approve Stage A criteria/count: ________ (requires `fleet_accounts` > 0)
- [ ] Request different cohort criteria
- [ ] Block until Fleet enrollment completed

## D-SE-05 — Manual run-once

- [ ] Authorize dry-run only
- [ ] Authorize dry-run + explicit Shadow persistence
- [ ] Do not authorize

## D-SE-06 — Runtime flag

- [ ] Keep `v67_shadow_runtime_enabled=false`
- [ ] Authorize `true` for controlled observation on named env only

## D-SE-07 — Scheduler flag

- [ ] Keep `v67_shadow_scheduler_enabled=false`
- [ ] Authorize `true` only after Stage A success

## D-SE-08 — Scheduler frequency

- [ ] Keep 300 seconds
- [ ] Other: ________ seconds

## D-SE-09 — Observation start

- [ ] Authorize start only after all technical gates pass + separate command
- [ ] Do not authorize

## D-SE-10 — Emergency stop authority

Authorized operator(s): ________

## D-SE-11 — Monitoring cadence

Daily review time/cadence (UTC): ________

## D-SE-12 — Data retention

- [ ] Keep indefinitely during observation
- [ ] Choose duration: ________
- [ ] Decide later with **no auto-delete**

## D-SE-13 — Dangerous mismatch threshold

- [ ] Remain **UNRATIFIED**
- [ ] Separate later decision only

## D-SE-14 — Frontend

- [ ] Remain deferred
- [ ] Authorize separate future frontend phase later

## D-SE-15 — Human/Native Contacts

- [ ] Remain deferred until valid Shadow milestone
- [ ] Authorize planning only after Stage A/B

---

After answers, wait for a **separate explicit authorization command** for the exact named environment before any flag change.
