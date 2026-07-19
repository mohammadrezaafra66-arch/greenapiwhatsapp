# V33 MASTER PROMPT — Afrakala WhatsApp Sender
## Fix the pending-stall root cause, enforce the 2-cold-account ceiling, clean orphaned tasks, and cap reminders at exactly 2 (then stop)

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking questions and
> WITHOUT waiting for approval. After each PART: run a heavy test suite and verify it
> works; only advance once every test passes. Commit and push each PART separately.
> Produce a final report.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main — V29/V30/V31
merged; V32 (unifying reminder TEXT variety, same as V31 did for asks) may already be
in-flight or done — check `git log` first and build on top of whatever is actually there;
do not redo V32's work if it's already landed, just make sure this prompt's PART 4 reuses
whatever the current reminder-generation function is (varied or not) rather than assuming
either state.

**Three issues surfaced by the last diagnostic that this prompt must resolve together,
since they all affect whether the ask→remind→thank-you loop actually works:**
1. Most `warmup_helper_task` rows are stuck `pending` (the ask/reminder/thank-you cycle
   isn't progressing for most contacts) — root cause unknown, investigate first.
2. Every contact is currently paired to all 3 cold instances, violating the intended
   "at most 2 cold accounts per contact" ceiling (a comment in `warmup_helpers.py` says
   this should be enforced in the service layer, but the DB only blocks exact duplicate
   pairs, not a 3rd distinct one).
3. 6 orphaned `warmup_helper_task` rows reference 2 deleted `warmup_helper` (contact) ids.

**Plus the user's new explicit requirement:**
4. Reminders are currently capped at ONE. Change this to **exactly 2 reminders maximum**,
   then STOP — never send a 3rd reminder or keep re-asking for that same (contact,
   cold_instance) task if the contact still hasn't completed it after 2 reminders.
   Completion (the contact actually messaging the assigned cold account) at ANY point —
   before, between, or after either reminder — still triggers exactly one thank-you
   (existing behavior) and the existing completion-escalation (auto-assign 2 new cold
   accounts, from V30 PART 4) unchanged.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only stays intact.
2. **Do NOT touch ngrok/webhook wiring, the mesh (V17–V25), V26 group-monitoring, V27
   anti-ban hardening, or the Telegram platform.** This is additive/refining to V29/V30/V31
   («همکاری تیمی») only.
3. **Do not silently delete or reassign data without reporting exactly what was changed
   and why.** For the orphaned-task cleanup and the 3-cold-per-contact reconciliation,
   report precisely which rows were removed/kept and the reasoning, in the final report.
4. **Every send continues to route through `warmup_helper_engine`'s existing
   `can_send_now` (V27) + shared `peer_pacer`, plus V30's 20-min/09–19-window rules.** No
   new/parallel send path.
5. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
6. **Commit + push each PART separately** (`V33 PART N: ...`).

### WORKFLOW PER PART
Investigate the ACTUAL current code/data first (don't assume) → implement → write/extend
tests → run the FULL existing test suite → verify zero regressions → commit + push → next
PART.

---

## PART 1 — Investigate + fix why most `warmup_helper_task` rows are stuck `pending`

### 1.1 Root-cause investigation (do this before any fix)
- Check, in order, the most likely causes: (a) the global/per-sender «همکاری تیمی» toggle
  state for the affected contacts' sender(s), (b) the `next_ask_at`/pacing-gate logic (is
  it correctly advancing, or stuck comparing against a wrong timezone/column?), (c) the
  09:00–19:00 work-hours window logic (is it perhaps miscalculating and treating valid
  times as out-of-window?), (d) the 20-minute per-sender ask-spacing gate (is it perhaps
  never releasing due to a bug?), (e) any exception being silently swallowed in the tick
  that processes pending tasks. Report the actual confirmed root cause(s) — there may be
  more than one contributing factor.

### 1.2 Fix
- Fix the confirmed root cause(s). Do not guess-patch multiple things without confirming
  which one(s) are actually responsible.

### 1.3 Tests
A test reproducing the exact stuck scenario (seed the same conditions found in 1.1) now
correctly progresses a pending task to `asked` within the expected window. Run full suite.
Commit + push `V33 PART 1: fix root cause of tasks stuck pending`.

---

## PART 2 — Enforce the 2-cold-account-per-contact ceiling (service + DB layer)

### 2.1 Enforce going forward
- Add a real enforcement (not just a comment) at the service layer AND, where feasible, a
  DB-level check so a contact can never be paired to more than 2 distinct cold instances.
  Reject a 3rd assignment attempt with a clear Persian error.

### 2.2 Reconcile existing violating rows
- For every contact currently paired to 3 cold instances, decide and apply a clear,
  reported rule for which pairing to drop (e.g., keep the 2 most-recently-active/most-
  advanced threads, drop the least-active one) — do NOT silently pick arbitrarily; log
  and report, per contact, which cold-instance pairing was removed and why. If any dropped
  pairing has an active/in-progress thread, note this explicitly in the report so the user
  can review before assuming it's fine.

### 2.3 Tests
A 3rd assignment attempt is rejected going forward; the reconciliation correctly reduces
every currently-3-paired contact down to 2, with the dropped pairing logged; no thread data
is silently lost (paused, not deleted, if there's any doubt).
Run full suite. Commit + push `V33 PART 2: enforce 2-cold-account ceiling + reconcile existing violations`.

---

## PART 3 — Clean up orphaned `warmup_helper_task` rows

### 3.1 Investigate then clean
- Confirm the 2 orphaned `helper_id`s (pointing to deleted `warmup_helper` rows) and their
  6 associated task rows. Since they reference contacts that no longer exist, remove these
  orphaned task rows (they can't sensibly progress — there's no valid contact to message).
  Report exactly which rows were removed (helper_id, cold_instance_id, task status at time
  of removal).

### 3.2 Prevent recurrence
- Add a foreign-key constraint or equivalent safeguard so deleting a `warmup_helper` row in
  the future either cascades to its tasks or is blocked while tasks exist — pick whichever
  is safer (reject deletion of a contact with active tasks, with a clear Persian message,
  is the safer default) and implement it.

### 3.3 Tests
The 6 known orphaned rows are removed; a fresh attempt to delete a contact with active
tasks is now handled safely (blocked or cascaded, per the chosen design) rather than
leaving new orphans.
Run full suite. Commit + push `V33 PART 3: clean up orphaned tasks + prevent recurrence`.

---

## PART 4 — Cap reminders at exactly 2, then stop (terminal no-response state)

### 4.1 Logic
- Change the reminder flow: ask fires → wait the existing window (45–60 min) → if not
  done, send reminder #1 (reuse whatever the CURRENT reminder-generation function is —
  check whether V32's AI-varied version already landed; if so use it, if not use the
  existing static one, but do not hardcode against either assumption) → wait the same
  window again → if still not done, send reminder #2 (final) → wait the same window again
  → if STILL not done, mark that specific (contact, cold_instance) task with a terminal
  status (e.g. `no_response`) and STOP — never send a 3rd reminder or re-ask for that same
  task. This terminal state should NOT block the contact from being asked about a
  DIFFERENT cold account in the future (it closes out only that specific task, not the
  contact overall).
- Completion (webhook detects the contact messaged the assigned cold account) at ANY point
  — before, between, or after either reminder, or even after the terminal `no_response`
  state is set — still triggers exactly one thank-you and the existing completion-
  escalation (V30 PART 4's auto-assignment of 2 new cold accounts), unchanged. (If
  completion is detected after `no_response` was already set, still honor it — better to
  thank a late responder than to miss it.)

### 4.2 Tests
A task with zero responses across the full window sequence gets exactly 2 reminders, then
transitions to `no_response` and never fires a 3rd; completion at any stage (before any
reminder, between the two reminders, or after both) correctly triggers exactly one
thank-you + the existing 2-new-cold-account escalation; a late completion after
`no_response` still triggers the thank-you; a different task for the same contact (a
different cold account) is unaffected by one task reaching `no_response`.
Run full suite. Commit + push `V33 PART 4: cap reminders at 2, then stop (terminal no-response state)`.

---

## PART 5 — Final wiring + full regression pass

### 5.1 Wiring
- Confirm PART 1's fix means previously-stuck contacts now actually progress through
  ask → (reminder ×0–2) → done/no_response, end to end.
- Confirm the reconciled 2-cold-account ceiling from PART 2 doesn't break any in-progress
  thread for the pairings that were kept.

### 5.2 Tests
Full end-to-end simulation: a previously-stuck contact now gets its ask sent; if it
doesn't respond, gets exactly 2 reminders then stops; if it does respond, gets thanked and
escalated with 2 new cold accounts (respecting the 2-cold ceiling — i.e., if it's already
at 2, no further auto-assignment happens, per PART 2's ceiling). Re-run the FULL
pre-existing suite (V17–V32) to confirm zero regressions.
Run full suite. Commit + push `V33 PART 5: final wiring + full regression pass`.

---

## FINAL REPORT
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- PART 1: the actual confirmed root cause(s) of the pending-stall, and the fix.
- PART 2: exactly which contacts/pairings were reconciled from 3→2 cold accounts, and why
  each specific pairing was dropped.
- PART 3: exactly which orphaned rows were removed, and the new safeguard against future
  orphans.
- PART 4: confirm the reminder cap is now exactly 2, with a terminal `no_response` state,
  and that completion always still triggers a thank-you regardless of timing.
- Confirm: polling never enabled; ngrok/webhook untouched; mesh/V26/V27/Telegram code
  unchanged; every send still routes through the existing gates/pacer; nothing was
  silently deleted without being reported.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
Fixing the pending-stall is the most important part of this prompt — a reminder cap or a
cold-account ceiling doesn't matter much if the underlying loop wasn't actually running for
most contacts in the first place. Once this deploys, watch a handful of contacts over the
next day to confirm the full ask → reminder(s) → done/no_response cycle behaves as
expected before assuming the whole roster is healthy.