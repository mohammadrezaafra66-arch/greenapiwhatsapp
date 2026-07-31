# V41 MASTER PROMPT — Afrakala WhatsApp Sender
## Recovery re-warm of 7105325764 via the existing mesh engine, per Green API's exact 10-day guidance

> MODE: FULLY AUTONOMOUS, RESUMABLE ACROSS SESSION LIMITS. Execute every PART end-to-end
> WITHOUT asking questions and WITHOUT waiting for approval. After each PART: run a heavy
> test suite and verify it works; only advance once every test passes. Commit and push
> each PART separately. If you hit a usage/session limit mid-part, stop cleanly; on the
> next invocation, run "git log --oneline -15" first and resume from the next incomplete
> PART rather than restarting.
>
> OUTPUT LANGUAGE: report to the user in English only, per this project's CLAUDE.md rule.
> All in-app UI strings stay Persian/RTL as always.

---

## 0. CONTEXT (read first)

Project: C:\Users\AFRA\Desktop\bots\claudegreenapi
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, V17 through
V40 merged (mesh warm-up state machine, V27 anti-ban, Team Collaboration V28-V39
including the universal 24h connect-cooldown and hard 14-day sender-eligibility gate,
V40 Story product analysis).

BACKGROUND: instance 7105325764 (9122270261, the primary/highest-warmth account) had a
clean 19-day history, then its linked devices (a laptop WhatsApp Web session AND the
Green API session) both dropped simultaneously - most likely because the physical phone
itself went offline (dead battery / no signal) for a period, which causes WhatsApp to
disconnect ALL linked devices as a safety behavior. Upon reconnecting via Green API only,
it received yellowCard status 24 seconds later. Green API support (ticket response)
confirmed the timing, explained the phone-offline mechanism, and gave a SPECIFIC 10-day
recovery sequence, quoted here for exact implementation (paraphrased for scope, not the
literal support-ticket wording):

  Day 1: do not link/authorize the instance at all.
  Day 2: authorize the instance, but send NOTHING via the API.
  Days 3-5 (3 days): OTHER real accounts message this number, roughly every 2 hours
    (receiving-only phase).
  Then: the number starts replying too, also roughly every 2 hours, to contacts already
    in its contact list.
  Over the following 7 days: gradually increase message flow from about 12 up to 100
    messages/day.
  After 10 days total: the number is considered much more ban-resistant.
  If ANYTHING disrupts this (reinstalling the app, moving the account to a different
    phone, another disconnect, etc.) during the process, RESTART THE WHOLE SEQUENCE FROM
    DAY 1 - do not continue from where it left off.
  Also: if the account then goes UNUSED for 14 days after finishing, warmth degrades again
    - so once graduated, keep it lightly active rather than fully idle.

The user has decided: re-warm 7105325764 from scratch using the EXISTING mesh state
machine (COOLDOWN -> RECEIVING -> REPLYING -> RAMPING -> MATURING -> GRADUATED), rather
than inventing a new system. Mesh stays globally disabled for every OTHER account (the
two previously-problematic numbers, 770022682882 and 770022683837, and anything else)
- this is a scoped, single-account exception, not a global mesh re-enable.

### NON-NEGOTIABLE GUARDRAILS
1. NEVER enable Green API polling. Webhook-only stays intact.
2. Do NOT re-enable mesh for any account other than 7105325764. Confirm, before and after
   every change, that every other warmup_enrollment row's is_enabled stays exactly as it
   was (false) unless the user explicitly asks otherwise later.
3. Do NOT touch ngrok/webhook wiring. Do NOT weaken the V27 chain-ban breaker, the V39
   universal connect-cooldown, or the V39 14-day sender-eligibility gate for any account.
4. Reuse the existing mesh state machine and its day-based progression logic - do not
   build a second, parallel warm-up system. Only add a distinct "recovery mode" variant if
   PART 1's investigation finds the existing general onboarding timeline doesn't already
   match Green API's specific numbers above (day boundaries, the ~2h messaging cadence,
   the 12-to-100 7-day ramp).
5. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
6. Commit + push each PART separately ("V41 PART N: ...").

### WORKFLOW PER PART
Investigate the ACTUAL current mesh state machine, its day thresholds, its peer-selection
logic, and 7105325764's current Team Collaboration sender assignments FIRST -> extend/fix
only where a real gap exists -> write/extend tests -> run the FULL existing test suite ->
verify zero regressions -> commit + push -> next PART.

---

## PART 1 - Investigate: does the existing mesh timeline match Green API's exact recovery sequence?

### 1.1 Investigate
- Read the existing mesh state machine's day-index thresholds and messaging cadence for
  each state (COOLDOWN, RECEIVING, REPLYING, RAMPING, MATURING, GRADUATED). Compare them,
  day by day, against Green API's stated sequence above (day 1 no-link, day 2 authorize-
  only, days 3-5 receiving every ~2h, then replying every ~2h, 7-day ramp 12->100,
  graduated at day 10).
- Report exactly where they match and where they differ.

### 1.2 Decide and, if needed, add a "recovery mode"
- If the existing timeline already matches closely enough, use it as-is for this account
  - no new code needed for the schedule itself.
- If it meaningfully differs (e.g., different day boundaries, different messaging
  frequency, or a different ramp curve), add a "recovery" variant/flag on the enrollment
  (e.g., a `recovery_mode` boolean) that uses Green API's exact numbers above instead of
  the general onboarding defaults, without changing behavior for any other/future
  enrollment that doesn't set this flag.

### 1.3 Tests
A test asserts the exact day-by-day expected state and messaging cadence for a
recovery-mode enrollment matches Green API's stated sequence precisely; a normal
(non-recovery) enrollment's existing behavior is unchanged (regression-checked).
Run full suite. Commit + push "V41 PART 1: confirm/add recovery-mode timeline matching Green API's exact sequence".

---

## PART 2 - Restart-on-disruption guard

### 2.1 Guard logic
- During this account's re-warm cycle, if ANYTHING disrupts it - a new disconnect event,
  a reconnect/relink, a state change to notAuthorized/yellowCard/blocked, or any other
  signal indicating the linked-device session churned again - reset its enrollment back to
  day_index=0 / COOLDOWN, rather than letting it continue from wherever it was. Log this
  reset clearly (reason + timestamp) so it's visible later.
- This guard should be general enough to apply to ANY mesh-enrolled account in
  recovery_mode (from PART 1), not hardcoded to this one instance id, so it holds if the
  user ever needs this recovery flow again for a different number later.

### 2.2 Tests
A recovery-mode enrollment mid-cycle (e.g., day 5) that experiences a fresh disconnect/
reconnect/incident event is reset to day_index=0/COOLDOWN, with the reset logged; an
enrollment with no disruption progresses normally through its days.
Run full suite. Commit + push "V41 PART 2: restart-on-disruption guard for recovery-mode enrollments".

---

## PART 3 - Pause 7105325764's Team Collaboration sender role for the duration

### 3.1 Pause, don't unassign
- While this account is in its mesh recovery cycle, it must NOT send anything as a Team
  Collaboration sender (asks/reminders/thank-yous/cold-replies) - confirm the existing
  V39 gates already block this given its current unhealthy/cooldown state, and keep it
  that way; do NOT unassign or reroute its 31 existing helper contacts elsewhere as part
  of this prompt (that's a separate decision for later) - they simply continue waiting,
  which is already the existing, correct behavior.
- Add a simple visible indicator (dashboard or log line) that this sender is currently
  "in mesh recovery" so it's clear why it's inactive as a TC sender, distinct from a
  generic "unhealthy" or "too young" reason.

### 3.2 Tests
While in recovery mode, 7105325764 cannot send via any Team Collaboration path (existing
gates confirmed sufficient, or fixed if a gap is found); the recovery-mode indicator shows
correctly wherever sender status is displayed.
Run full suite. Commit + push "V41 PART 3: confirm/indicate TC sender pause during mesh recovery".

---

## PART 4 - Peer selection + enrollment

### 4.1 Enroll 7105325764 into mesh, recovery mode, day 0
- Set its mesh enrollment: is_enabled=true, state=COOLDOWN, day_index=0, recovery_mode=true
  (from PART 1). Confirm every OTHER account's enrollment is_enabled remains false/
  unchanged (guardrail 2).
- Confirm the chain-ban breaker is not currently tripped before enabling; if it is, do NOT
  silently reset it - report this and stop, awaiting the user's explicit instruction (this
  is a real decision, not a mechanical step).

### 4.2 Peer selection
- Using the EXISTING peer-selection/warmth logic, report which currently-connected account
  is the safest available option to serve as 7105325764's peer (the "other real account"
  that messages it during the receiving phase). If NONE currently pass the existing
  peer-eligibility bar, report this clearly rather than silently picking an ineligible one
  - this is a case where the user may reasonably choose to relax the peer bar specifically
  for a controlled, closely-monitored recovery cycle (Green API's own guidance does not
  require a 14-day peer, only a real functioning number), but that relaxation must be an
  explicit, visible choice in the report, not a silent default.

### 4.3 Tests
Enrollment fields are set correctly; every other enrollment's is_enabled is confirmed
unchanged; the breaker-tripped case correctly halts and reports instead of proceeding; peer
selection reuses the existing warmth logic and reports its pick (or the "none qualify"
finding) accurately.
Run full suite. Commit + push "V41 PART 4: enroll 7105325764 in mesh recovery mode + peer selection".

---

## PART 5 - Dashboard visibility + final wiring

### 5.1 Visibility
- Make sure the existing mesh dashboard clearly shows: this account's recovery-mode
  status, current day-index, its assigned peer, and a clear "reset X times due to
  disruption" counter if PART 2's guard has ever fired for it.

### 5.2 Tests
Full end-to-end simulation: enroll at day 0 -> simulate the scripted 10-day progression
with the recovery-mode timeline -> confirm it reaches GRADUATED at the expected day only
if no disruption occurs -> confirm a simulated mid-cycle disruption correctly resets it to
day 0 -> confirm the TC sender pause holds throughout -> confirm no other account's mesh
enrollment was ever touched. Re-run the FULL pre-existing suite (V17-V40) to confirm zero
regressions.
Run full suite. Commit + push "V41 PART 5: dashboard visibility + final wiring".

---

## FINAL REPORT
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- PART 1: whether the existing mesh timeline already matched Green API's exact sequence,
  or what recovery-mode variant was added.
- PART 4: the selected peer (or the explicit "none qualify" finding, with the user's
  choice on whether to relax the peer bar for this cycle).
- Confirm: mesh remains disabled for every other account; the chain-ban breaker was not
  silently reset if it was tripped; the 31 existing Team Collaboration contacts for this
  sender are untouched (still waiting, not reassigned).
- Confirm: polling never enabled; ngrok/webhook untouched; no V27/V39 gate weakened.
- The list of pushed commits, and the redeploy reminder:
  "docker compose build frontend && docker compose up -d frontend" and
  "docker compose up -d --force-recreate worker-general worker-webhooks beat backend".

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
This treats 7105325764 exactly like a fresh number per Green API's own explicit guidance,
using infrastructure this project already has. The restart-on-disruption guard is the
most important piece - it is what actually enforces Green API's "start over if anything
changes" warning instead of relying on someone remembering to check.