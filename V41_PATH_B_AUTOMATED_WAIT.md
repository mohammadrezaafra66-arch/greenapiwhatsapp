# V41 PATH B — AUTOMATED WAIT-AND-APPLY FOR MESH RECOVERY ENROLLMENT
## Do not relax any rule; automatically apply the recovery enrollment for 7105325764 the moment both real conditions clear naturally

> MODE: FULLY AUTONOMOUS. Execute start to finish WITHOUT asking any question and
> WITHOUT waiting for approval. If you hit a usage/session limit mid-task, stop cleanly;
> on the next invocation, run "git log --oneline -20" AND "git status" first, and resume
> from the next incomplete step.
>
> OUTPUT LANGUAGE: report in English only. All in-app UI strings stay Persian/RTL.

---

## 0. CONTEXT (read first)

Project: C:\Users\AFRA\Desktop\bots\claudegreenapi
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, V41 PARTs 1-5
all committed and pushed (recovery-mode timeline, restart-on-disruption guard, TC sender
pause + indicator, enrollment + peer-selection script, dashboard visibility).

BACKGROUND: 7105325764's mesh recovery enrollment (per Green API's 10-day re-warm
guidance) has NOT yet been applied. A live preflight found TWO blocking conditions:
1. The chain-ban breaker is currently TRIPPED (by 7105325764's own yellowCard).
2. NO account currently passes the existing peer-eligibility bar (>=14 days connected,
   clean incident history) to serve as its mesh peer — every other account is either
   0-days-old (recently connected) or disconnected/dead.

THE USER'S EXPLICIT DECISION ("Path B"): do NOT relax the 14-day peer-eligibility rule.
Do NOT manually reset the breaker either. Instead: WAIT for both conditions to clear
NATURALLY (the breaker ages out / gets legitimately resolved, and/or an account such as
770022683809 / 770022683810 / 770022683838 naturally crosses the 14-day-clean threshold
around 2026-07-29, if they stay connected and incident-free) — and the moment BOTH
conditions are genuinely satisfied, the recovery enrollment should apply AUTOMATICALLY,
without requiring the user to manually re-run a check every day.

### NON-NEGOTIABLE GUARDRAILS
1. NEVER enable Green API polling. Webhook-only stays intact.
2. Do NOT relax the peer-eligibility bar. Do NOT reset the chain-ban breaker yourself,
   ever, under any circumstance in this prompt. Both must clear through the EXISTING,
   unmodified rules — this prompt only adds AUTOMATED WAITING AND CHECKING, never a
   rule change or an override.
3. Do NOT re-enable mesh for any account OTHER than 7105325764 as part of this
   automated check. Before and after every check, confirm every other
   warmup_enrollment row's is_enabled is unchanged.
4. Reuse the EXISTING preflight/enrollment logic in
   backend/app/services/warmup_recovery_enroll.py and
   backend/scripts/v41_enroll_recovery.py exactly as already built and tested — do not
   reimplement the eligibility checks; this prompt only automates WHEN that existing
   logic gets invoked and applied.
5. Do NOT touch V40 story-analysis code or V42 AI-model-discovery code.
6. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
7. Commit + push each PART separately.

---

## PART 1 — Scheduled automatic recheck task

### 1.1 Build
- Add a new Celery beat task (reasonable cadence — once daily is sufficient given the
  timeframes involved; do not poll more frequently than needed) that:
  1. Runs the EXISTING preflight logic from warmup_recovery_enroll.py /
     v41_enroll_recovery.py's dry-run path for 7105325764 — checking, using the
     unmodified existing rules, whether (a) the chain-ban breaker is currently NOT
     tripped, AND (b) at least one account now passes the existing peer-eligibility bar.
  2. If EITHER condition is still not met: do nothing further this run, just log a
     one-line status (e.g., "recovery enrollment still blocked: breaker=<tripped/clear>,
     peer=<none/found X>") so there's a visible history of when conditions changed.
  3. If BOTH conditions are met: automatically APPLY the enrollment for 7105325764
     exactly as the existing script would (is_enabled=true, state=COOLDOWN, day_index=0,
     recovery_mode=true, peer=the found eligible account) — reusing the existing
     enroll_recovery_mode function, not a new implementation. Log this clearly as a
     genuine state change (old status -> newly enrolled, with the peer chosen and why).
     After this first successful auto-apply, this task should stop re-checking for this
     specific account (it only needs to fire once) — but it should not error or cause any
     issue if it happens to run again while already enrolled (must be idempotent: if
     7105325764 is already enrolled in recovery mode, running this task again is a safe
     no-op).

### 1.2 Guardrail checks inside the task itself
- Before applying anything, the task must re-verify that every OTHER account's mesh
  enrollment is_enabled is still false — if any other account has somehow been enabled
  (by any other process), abort the auto-apply for this run, log a loud warning, and do
  NOT proceed (this protects against an unrelated change silently combining with this
  automation in an unintended way).

### 1.3 Tests
A test where the breaker is tripped and/or no peer qualifies confirms the task logs
status and takes no action. A test where both conditions are met confirms the task
applies the enrollment exactly once, correctly, with the right peer, and logs the
transition clearly. A test confirms running the task again after a successful
enrollment is a safe no-op (idempotent). A test confirms the "abort if another
account's enrollment changed unexpectedly" guard works. Run the FULL existing suite and
confirm zero regressions.
Run full suite. Commit + push "V41 Path B PART 1: scheduled automatic recheck + auto-apply when both conditions naturally clear".

---

## PART 2 — Visibility for the pending/waiting state

### 2.1 Dashboard note
- On the existing mesh dashboard (from V41 PART 5), when 7105325764 is not yet enrolled
  in recovery mode, show a clear, simple pending status reflecting the LAST recheck's
  findings (from PART 1.1's logged status), e.g. "در انتظار — بریکر: <فعال/پاک شده>،
  فرستنده‌ی همراه واجدشرایط: <یافت نشد/یافت شد>" — so the user can see current status
  at a glance without needing to ask for another diagnostic each time.

### 2.2 Tests
The dashboard correctly reflects the most recent recheck's findings for the pending
state; once auto-applied, it switches to showing the normal in-progress recovery view
(day-index, peer, etc.) from V41 PART 5, unchanged.
Run full suite (backend + frontend). Commit + push "V41 Path B PART 2: dashboard visibility for the pending auto-apply state".

---

## PART 3 — Final wiring + regression pass

### 3.1 Tests
Full end-to-end simulation: seed a tripped breaker + no eligible peer -> confirm the
task does nothing and logs status; clear the breaker and make one account eligible ->
confirm the task auto-applies the enrollment correctly on its next scheduled run, with
the right peer, correctly logged; confirm re-running afterward is a safe no-op; confirm
no other account's enrollment was ever touched throughout. Re-run the FULL pre-existing
suite to confirm zero regressions.
Run full suite. Commit + push "V41 Path B PART 3: final wiring + full regression pass".

---

## FINAL REPORT
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- Confirm: the new scheduled task NEVER relaxes the peer bar and NEVER resets the
  breaker itself — it only waits and checks using the existing, unmodified rules.
- Confirm: every other account's mesh enrollment remains untouched throughout.
- The exact current status (as of this report): is the breaker tripped or clear right
  now, and does any account currently qualify as peer, per a fresh run of the check.
- Confirm: polling never enabled; ngrok/webhook untouched; V40/V42 code untouched.
- The list of pushed commits, and the redeploy reminder:
  "docker compose build frontend && docker compose up -d frontend" and
  "docker compose up -d --force-recreate worker-general worker-webhooks beat backend".

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
This does not speed anything up and does not take on any new risk — it simply removes
the need to manually re-check every day. The moment 7105325764's situation is genuinely
safe by the project's own existing standards, the recovery cycle begins automatically;
until then, nothing changes.