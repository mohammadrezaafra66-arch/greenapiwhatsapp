# V50 MASTER PROMPT — Afrakala WhatsApp Sender
## Scheduled auto-fetch for stories + multi-account resilience

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
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, through V49.

A diagnostic confirmed two real structural weaknesses in story fetching:
1. Stories are fetched PURELY on-demand — only when a human opens/refreshes the
   `/statuses` page's incoming tab. There is no scheduled background task. If nobody
   visits the page for days, stories simply never refresh, even though the mechanism
   itself works fine.
2. Every story ever fetched (1201/1201 rows) came from exactly ONE hardcoded account —
   whichever account is currently `is_default = true` (`7105325764`). The frontend calls
   `Api.incoming()` with no account parameter, so it always resolves to that single
   account regardless of what's selected elsewhere in the UI. If that one account is
   ever offline (as happened during its recent mesh-recovery period), story fetching
   stops entirely with zero fallback — even though several OTHER accounts are currently
   connected and authorized (e.g. 770022693143/142/144/145, connected today) and could
   plausibly see different contacts' stories through their own separate contact lists.

THIS PROMPT fixes both: add a scheduled background fetch, and cycle through every
currently-healthy connected account (not just the one default) — which also plausibly
IMPROVES coverage (different accounts likely see different contacts' stories), not just
resilience.

### NON-NEGOTIABLE GUARDRAILS
1. Reuse the EXACT existing fetch function/service already used by the manual
   `/statuses/incoming` endpoint — call it once per eligible account in a loop, do not
   duplicate its logic.
2. NEVER enable Green API polling for anything unrelated to this feature — this is
   specifically about the story-fetch mechanism, which already uses Green API's own
   documented on-demand `getIncomingStatuses` method; do not touch or weaken the
   webhook-only guarantee for messages/other features.
3. Skip any account currently in mesh recovery mode (V41) or otherwise unhealthy
   (yellowCard/blocked/notAuthorized/in its 24h connect-cooldown) — even though reading
   incoming statuses is a read-only Green API call and unlikely to carry real ban risk,
   stay consistent with this project's established caution: a recovering account should
   have zero extra activity beyond its scripted recovery sequence.
4. Choose a conservative, sensible fetch interval — this is a real (if lightweight) API
   call per eligible account; investigate whether Green API documents any rate
   consideration for this specific method before picking a cadence, and default to
   something conservative (e.g., every 20-30 minutes) rather than aggressive polling.
5. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
6. Commit + push each PART separately ("V50 PART N: ...").

### WORKFLOW PER PART
Read the actual current fetch function/service and account-health-check utilities first
(don't assume) → extend → write/extend tests → run the FULL existing test suite → verify
zero regressions → commit + push → next PART.

---

## PART 1 — Multi-account fetch: extend the existing service to loop over eligible accounts

### 1.1 Investigate + extend
- Read the exact current fetch function behind `/statuses/incoming` (the one currently
  hardcoded to a single account via the frontend's no-argument call). Extend it (or add
  a thin wrapper) so it can be invoked for ANY given account, and build a
  `fetch_stories_for_all_eligible_accounts()` function that: lists every currently
  connected/authorized account, EXCLUDES any account that's unhealthy (per guardrail 3),
  and calls the existing per-account fetch for each, merging results into
  `received_statuses` (already keyed with `instance_id` per row, so no schema change
  needed there).
- Handle a single account's fetch failing gracefully (log and continue to the next
  account) — one account's problem must not abort fetching for the others.

### 1.2 Tests
Given a mix of healthy and unhealthy/recovering accounts, the function fetches only from
the healthy ones, merges results correctly with the right `instance_id` per row, and
one account's simulated failure doesn't prevent the others from being fetched.
Run full suite. Commit + push "V50 PART 1: multi-account story fetch (loop over eligible accounts)".

---

## PART 2 — Scheduled background fetch (Celery beat)

### 2.1 Investigate cadence
- Quickly check whether Green API documents any specific rate guidance for
  `getIncomingStatuses` (reuse any existing research/notes in this codebase about this
  method if present); if nothing specific is found, default to a conservative interval
  (e.g., every 20-30 minutes) rather than guessing something aggressive.

### 2.2 Add the scheduled task
- Add a new Celery beat entry that calls PART 1's
  `fetch_stories_for_all_eligible_accounts()` on the chosen interval, so stories refresh
  automatically even if nobody visits the page. Reuse the existing beat-schedule
  conventions already used elsewhere in `celery_app.py`.
- Ensure the manual on-page refresh button still works exactly as before (this is
  additive, not a replacement) — a human refreshing the page should still trigger an
  immediate fetch too, not just rely on waiting for the next scheduled run.

### 2.3 Tests
The scheduled task is correctly registered in the beat schedule at the chosen interval;
triggering it (in a test) calls PART 1's multi-account function; the existing manual
refresh path is unaffected (regression-checked).
Run full suite. Commit + push "V50 PART 2: scheduled automatic story fetch (Celery beat)".

---

## PART 3 — Final wiring + full regression pass + redeploy (execute it yourself)

### 3.1 Tests
Full end-to-end simulation: with the primary default account healthy plus 2-3 other
healthy accounts and one account correctly excluded (mesh recovery), a scheduled run
fetches from all eligible accounts and merges results correctly, without requiring any
page visit. Re-run the FULL pre-existing suite to confirm zero regressions.

### 3.2 Execute the redeploy yourself
Run:
```
docker compose build frontend
docker compose up -d frontend
docker compose up -d --force-recreate worker-general worker-webhooks beat backend
```
Verify live: the new beat entry is genuinely registered and fires on schedule (check
actual beat logs/timestamps after deploy, not just that the code was committed); a fresh
story appears in `received_statuses` from the scheduled run without anyone visiting the
page.

---

## FINAL REPORT
- Confirm PART 1's multi-account fetch works with real evidence (which accounts were
  actually eligible right now, and confirm at least one non-default account successfully
  contributed a fetch attempt).
- Confirm PART 2's scheduled task is genuinely live and fired at least once after
  redeploy, with a real timestamp.
- Confirm the manual refresh button still works exactly as before.
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- Confirm the redeploy was executed (not just recommended) and verified live.
- The list of pushed commits.

Then STOP and await review.