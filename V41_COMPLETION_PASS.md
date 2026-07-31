# V41 MASTER PROMPT (COMPLETION PASS) — Afrakala WhatsApp Sender
## Recovery re-warm of 7105325764 via the existing mesh engine, per Green API's exact 10-day guidance

> MODE: FULLY AUTONOMOUS, RESUMABLE ACROSS SESSION LIMITS. Execute every PART end-to-end
> WITHOUT asking questions and WITHOUT waiting for approval, EXCEPT the two explicit stop
> conditions named in PART 4. After each PART: run a heavy test suite and verify it works;
> only advance once every test passes. Commit and push each PART separately. If you hit a
> usage/session limit mid-part, stop cleanly; on the next invocation, run
> "git log --oneline -20" AND "git status" first, and resume from the next incomplete
> PART rather than restarting or redoing already-committed work.
>
> OUTPUT LANGUAGE: report to the user in English only, per this project's CLAUDE.md rule.
> All in-app UI strings stay Persian/RTL as always.

---

## PART 0 — Reconcile existing uncommitted work (do this FIRST, before anything else)

An earlier session left UNCOMMITTED, in-progress files related to this same V41 effort.
Do not assume they are correct or complete — verify and decide deliberately.

### 0.1 Inspect
- Run `git status` and `git log --oneline -20` to confirm the current tree state.
- Read the following uncommitted files in full, if they exist:
  - `backend/app/services/warmup_recovery_enroll.py`
  - `backend/scripts/v41_enroll_recovery.py`
  - `backend/tests/test_v41_part4.py`
  - any other uncommitted `.py` file touching mesh enrollment, recovery mode, or
    7105325764 specifically.
- Also confirm: has V40's normalize_status media-type bug fix (Green API's real "type":
  "incoming" field being misread as a media type, breaking story image download and
  vision analysis) already been applied in an earlier session? Check for it; if it's
  still broken, that is a SEPARATE, already-known issue — do NOT fix it as part of this
  V41 prompt (stay scoped to V41), just note its state in your final report so it isn't
  lost track of.

### 0.2 Decide: salvage or restart
- If the uncommitted files correctly implement part of PART 4 below (peer
  enrollment/recovery-mode setup) and are consistent with everything else in this
  prompt, continue building on them.
- If they conflict with this prompt's design, are incomplete in a way that's easier to
  redo than patch, or you're not confident they're correct, discard them (do not leave
  half-correct code lying around) and build PART 4 cleanly per the spec below.
- Report which choice you made and why, before proceeding.

### 0.3 Tests
No specific test for this part beyond confirming the tree is in a known, clean, understood
state before PART 1 begins. Commit nothing yet — this is pure reconnaissance.

---

## 0.4 CONTEXT (full background, read before building)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main, V17 through
V40 merged (mesh warm-up state machine, V27 anti-ban, Team Collaboration V28-V39
including the universal 24h connect-cooldown and hard 14-day sender-eligibility gate,
V40 Story product analysis).

BACKGROUND: instance 7105325764 (9122270261, the primary/highest-warmth account) had a
clean 19-day history, then its linked devices (a laptop WhatsApp Web session AND the
Green API session) both dropped simultaneously — most likely because the physical phone
itself went offline (dead battery / no signal) for a period, which causes WhatsApp to
disconnect ALL linked devices as a safety behavior. Upon reconnecting via Green API only,
it received yellowCard status 24 seconds later. Green API support confirmed the timing,
explained the phone-offline mechanism, and gave a SPECIFIC 10-day recovery sequence,
paraphrased here for exact implementation:

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
    DAY 1 — do not continue from where it left off.
  Also: if the account then goes UNUSED for 14 days after finishing, warmth degrades
    again — so once graduated, keep it lightly active rather than fully idle.

The user has decided: re-warm 7105325764 from scratch using the EXISTING mesh state
machine (COOLDOWN -> RECEIVING -> REPLYING -> RAMPING -> MATURING -> GRADUATED), rather
than inventing a new system. Mesh stays globally disabled for every OTHER account (the
two previously-problematic numbers, 770022682882 and 770022683837, and anything else) —
this is a scoped, single-account exception, not a global mesh re-enable.

### NON-NEGOTIABLE GUARDRAILS
1. NEVER enable Green API polling. Webhook-only stays intact.
2. Do NOT re-enable mesh for any account other than 7105325764. Confirm, before and after
   every change, that every other warmup_enrollment row's is_enabled stays exactly as it
   was (false) unless the user explicitly asks otherwise later.
3. Do NOT touch ngrok/webhook wiring. Do NOT weaken the V27 chain-ban breaker, the V39
   universal connect-cooldown, or the V39 14-day sender-eligibility gate for any account.
4. Reuse the existing mesh state machine and its day-based progression logic — do not
   build a second, parallel warm-up system. Only add a distinct "recovery mode" variant if
   PART 1's investigation finds the existing general onboarding timeline doesn't already
   match Green API's specific numbers above (day boundaries, the ~2h messaging cadence,
   the 12-to-100 7-day ramp).
5. Stay scoped to V41. Do not fix or touch the V40 story-media-type bug (normalize_status)
   as part of this pass, even if you notice it — that is tracked separately.
6. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
7. Commit + push each PART separately (`V41 PART N: ...`).

### WORKFLOW PER PART
Investigate the ACTUAL current mesh state machine, its day thresholds, its peer-selection
logic, and 7105325764's current Team Collaboration sender assignments FIRST → extend/fix
only where a real gap exists → write/extend tests → run the FULL existing test suite →
verify zero regressions → commit + push → next PART.

---

## PART 1 — Confirm/add recovery-mode timeline matching Green API's exact sequence

### 1.1 Investigate
- Read the existing mesh state machine's day-index thresholds and messaging cadence for
  each state (COOLDOWN, RECEIVING, REPLYING, RAMPING, MATURING, GRADUATED). Compare them,
  day by day, against Green API's stated sequence above (day 1 no-link, day 2 authorize-
  only, days 3-5 receiving every ~2h, then replying every ~2h, 7-day ramp 12->100,
  graduated at day 10).
- Report exactly where they match and where they differ.

### 1.2 Decide and, if needed, add a "recovery mode"
- If the existing timeline already matches closely enough, use it as-is for this account —
  no new code needed for the schedule itself.
- If it meaningfully differs, add a "recovery" variant/flag on the enrollment (e.g., a
  `recovery_mode` boolean) that uses Green API's exact numbers above instead of the
  general onboarding defaults, without changing behavior for any other/future enrollment
  that doesn't set this flag.

### 1.3 Tests
A test asserts the exact day-by-day expected state and messaging cadence for a
recovery-mode enrollment matches Green API's stated sequence precisely; a normal
(non-recovery) enrollment's existing behavior is unchanged (regression-checked).
Run full suite. Commit + push `V41 PART 1: confirm/add recovery-mode timeline matching Green API's exact sequence`.

---

## PART 2 — Restart-on-disruption guard

### 2.1 Guard logic
- During this account's re-warm cycle, if ANYTHING disrupts it — a new disconnect event,
  a reconnect/relink, a state change to notAuthorized/yellowCard/blocked, or any other
  signal indicating the linked-device session churned again — reset its enrollment back to
  day_index=0 / COOLDOWN, rather than letting it continue from wherever it was. Log this
  reset clearly (reason + timestamp) so it's visible later.
- This guard should be general enough to apply to ANY mesh-enrolled account in
  recovery_mode (from PART 1), not hardcoded to this one instance id, so it holds if the
  user ever needs this recovery flow again for a different number later.

### 2.2 Tests
A recovery-mode enrollment mid-cycle (e.g., day 5) that experiences a fresh disconnect/
reconnect/incident event is reset to day_index=0/COOLDOWN, with the reset logged; an
enrollment with no disruption progresses normally through its days.
Run full suite. Commit + push `V41 PART 2: restart-on-disruption guard for recovery-mode enrollments`.

---

## PART 3 — Pause 7105325764's Team Collaboration sender role for the duration

### 3.1 Pause, don't unassign
- While this account is in its mesh recovery cycle, it must NOT send anything as a Team
  Collaboration sender (asks/reminders/thank-yous/cold-replies) — confirm the existing
  V39 gates already block this given its current unhealthy/cooldown state, and keep it
  that way; do NOT unassign or reroute its 31 existing helper contacts elsewhere as part
  of this prompt (that's a separate decision for later) — they simply continue waiting,
  which is already the existing, correct behavior.
- Add a simple visible indicator (dashboard or log line) that this sender is currently
  "in mesh recovery" so it's clear why it's inactive as a TC sender, distinct from a
  generic "unhealthy" or "too young" reason.

### 3.2 Tests
While in recovery mode, 7105325764 cannot send via any Team Collaboration path (existing
gates confirmed sufficient, or fixed if a gap is found); the recovery-mode indicator shows
correctly wherever sender status is displayed.
Run full suite. Commit + push `V41 PART 3: confirm/indicate TC sender pause during mesh recovery`.

---

## PART 4 — Peer selection + enrollment (EXPLICIT STOP CONDITIONS APPLY HERE)

### 4.1 Enroll 7105325764 into mesh, recovery mode, day 0
- Set its mesh enrollment: is_enabled=true, state=COOLDOWN, day_index=0, recovery_mode=true
  (from PART 1). Confirm every OTHER account's enrollment is_enabled remains false/
  unchanged (guardrail 2).
- **STOP CONDITION 1:** Confirm the chain-ban breaker is not currently tripped before
  enabling; if it IS tripped, do NOT silently reset it — stop this part, report the
  situation clearly, and await the user's explicit instruction before proceeding further.

### 4.2 Peer selection
- Using the EXISTING peer-selection/warmth logic, report which currently-connected account
  is the safest available option to serve as 7105325764's peer (the "other real account"
  that messages it during the receiving phase).
- **STOP CONDITION 2:** If NONE currently pass the existing peer-eligibility bar, do NOT
  silently pick an ineligible one — report this clearly and stop, awaiting the user's
  explicit decision on whether to relax the peer bar specifically for this controlled,
  closely-monitored recovery cycle (Green API's own guidance does not require a 14-day
  peer, only a real functioning number, but this relaxation must be an explicit, visible
  choice made by the user, not a silent default).

### 4.3 Tests
Enrollment fields are set correctly; every other enrollment's is_enabled is confirmed
unchanged; the breaker-tripped case correctly halts and reports instead of proceeding; peer
selection reuses the existing warmth logic and reports its pick (or the "none qualify"
finding) accurately.
Run full suite. Commit + push `V41 PART 4: enroll 7105325764 in mesh recovery mode + peer selection`
(only after both stop conditions are cleared — either they didn't trigger, or the user
explicitly resolved them).

---

## PART 5 — Dashboard visibility + final wiring

### 5.1 Visibility
- Make sure the existing mesh dashboard clearly shows: this account's recovery-mode
  status, current day-index, its assigned peer, and a clear "reset X times due to
  disruption" counter if PART 2's guard has ever fired for it.

### 5.2 Tests
Full end-to-end simulation: enroll at day 0 → simulate the scripted 10-day progression
with the recovery-mode timeline → confirm it reaches GRADUATED at the expected day only
if no disruption occurs → confirm a simulated mid-cycle disruption correctly resets it to
day 0 → confirm the TC sender pause holds throughout → confirm no other account's mesh
enrollment was ever touched. Re-run the FULL pre-existing suite (V17-V40) to confirm zero
regressions.
Run full suite. Commit + push `V41 PART 5: dashboard visibility + final wiring`.

---

## FINAL REPORT
- PART 0: what was found in the uncommitted files, and whether it was salvaged or
  discarded, and why.
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- PART 1: whether the existing mesh timeline already matched Green API's exact sequence,
  or what recovery-mode variant was added.
- PART 4: the selected peer (or the explicit "none qualify" finding awaiting the user's
  decision), and whether the breaker was tripped (and thus whether PART 4 actually
  completed or is paused awaiting the user).
- Confirm: mesh remains disabled for every other account; the 31 existing Team
  Collaboration contacts for this sender are untouched (still waiting, not reassigned).
- Confirm: polling never enabled; ngrok/webhook untouched; no V27/V39 gate weakened; the
  V40 story-media bug was left untouched (out of scope for this pass).
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
This treats 7105325764 exactly like a fresh number per Green API's own explicit guidance,
using infrastructure this project already has. The restart-on-disruption guard is the
most important piece — it is what actually enforces Green API's "start over if anything
changes" warning instead of relying on someone remembering to check.