# V49 MASTER PROMPT — Afrakala WhatsApp Sender
## Fix the 2-day data purge + reconcile date-range UI + close a detection gap

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
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, through V48.

A recent diagnostic confirmed a real, live scheduled job that PERMANENTLY DELETES
`product_mention_logs` rows (and possibly related story-analysis data) after just 2
DAYS — not a filter, an actual purge. This directly conflicts with V43's own date-range
expansion (7/14/30/60/90/180/365 days + "all time"): none of those wider windows can
ever show more than 2 days of real history, because the underlying rows are already
gone. The user has decided: retain this data for 90 DAYS going forward (not
indefinitely, not 365 — 90 days is the deliberate choice). A separate, smaller gap was
also found: `detect_product_mentions` misses some real product listings phrased as
"<capacity> <brand>" without a standard model code (e.g. a real example: "۳۰هزار گلد
موتور بزرگ ویتالی").

### NON-NEGOTIABLE GUARDRAILS
1. Reuse the existing purge/retention job's mechanism and the existing detection
   pipeline — extend them, do not build parallel systems.
2. Do NOT weaken the V45 own-number exclusion (which correctly filters out the
   business's own promotional blasts) while fixing the detection gap — a broader
   detection pattern must still respect that exclusion.
3. Any relaxed detection pattern must be tested against BOTH the real missed examples
   AND a set of clearly-non-product real messages, to confirm no new false positives are
   introduced.
4. NEVER enable Green API polling. Webhook-only stays intact.
5. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
6. Commit + push each PART separately ("V49 PART N: ...").

### WORKFLOW PER PART
Read the actual current purge job and detection code first (don't assume) → fix →
write/extend tests → run the FULL existing test suite → verify zero regressions →
commit + push → next PART.

---

## PART 1 — Fix the retention/purge job: 2 days → 90 days

### 1.1 Investigate
- Find the exact scheduled job/task that currently purges `product_mention_logs` (and
  confirm whether `story_product_analysis` and/or downloaded story media are also
  affected by the same or a related purge). Confirm its exact current interval/window
  value in the running configuration (not just what the code file says — this project
  has a known prior incident where a code change didn't match what was actually running
  until beat/workers were recreated; verify the LIVE behavior, not just the source).

### 1.2 Fix
- Change the retention window to 90 days for `product_mention_logs`. Decide, based on
  what PART 1.1 found, whether `story_product_analysis` and downloaded story media
  (`backend/.media/`) should share the same 90-day window or a different one — media
  storage was flagged before as "the only durable copy" of story images, so consider
  whether purging media after 90 days is desired or whether media should be retained
  longer/indefinitely while only the mention-log rows follow the 90-day rule (make a
  clear, reasoned choice and state it plainly in the report — don't silently assume).
- Ensure the fix is actually live after this PART's redeploy, not just committed — verify
  against the running beat schedule/config directly.

### 1.3 Tests
A test confirms the purge job's configured window is now 90 days (not 2); a test seeds
rows at ages just inside and just outside the 90-day boundary and confirms only the
older-than-90-days rows are purged; run full suite. Commit + push
"V49 PART 1: extend data retention from 2 days to 90 days".

---

## PART 2 — Reconcile the V43 date-range UI with the real 90-day ceiling

### 2.1 Fix the UI options
- V43 added date-range options up to 365 days and "all time." Since real retention is
  now 90 days, remove or adjust any option that would silently imply more history exists
  than actually can (e.g., 180 days, 365 days, "all time") — cap the meaningful options
  at 90 days going forward, so the UI never misleads the user about how far back data
  actually goes. Keep the smaller, still-valid options (7/14/30/60/90) as they are.
- If there's value in keeping a "90+" option that simply means "everything currently
  retained" (rather than removing entirely), that's an acceptable alternative — pick
  whichever is clearer for the user and explain the choice in the report.

### 2.2 Tests
The date-range dropdown no longer offers options that could never return more than 90
days of real data; selecting any remaining option returns correctly-bounded results; the
existing V44 search and V40 source-filter still work correctly alongside the adjusted
range options.
Run full suite (backend + frontend build/pure-module tests). Commit + push
"V49 PART 2: reconcile date-range UI options with the real 90-day retention ceiling".

---

## PART 3 — Close the detection gap for capacity+brand-style listings

### 3.1 Investigate and fix
- Read the exact current pattern/rule in `detect_product_mentions` (and
  `extract_unknown_products`) that currently misses listings phrased as
  "<capacity/size> <brand>" without a standard model code (e.g. the real example
  "۳۰هزار گلد موتور بزرگ ویتالی"). Determine whether the fix should be: relaxing an
  overly strict minimum model-code length/pattern requirement, adding a small brand-name
  lexicon (reusing whatever brand/catalog data already exists in this project, e.g. the
  Supabase catalog feed, rather than hardcoding a new brand list from scratch if one can
  be derived from existing data), or both.
- Apply the fix carefully — this must not weaken the V45 own-number exclusion, and must
  not start matching generic, non-product conversational text as a false positive.

### 3.2 Tests
The real previously-missed example(s) are now correctly detected; a set of clearly
non-product real messages (greetings, questions, logistics chat, etc.) are confirmed to
still NOT be falsely detected as product mentions after the relaxation; existing
correctly-detected examples remain correctly detected (no regression to already-working
detection).
Run full suite. Commit + push "V49 PART 3: close detection gap for capacity+brand-style product listings".

---

## PART 4 — Final wiring + full regression pass + redeploy (execute it yourself)

### 4.1 Tests
Full end-to-end simulation: a mention logged today and one logged 91 days ago — only the
91-day-old one is purged after the next scheduled purge run; the date-range UI reflects
the new options correctly; the previously-missed brand+capacity example is now detected
and correctly flows into the top-products report (respecting V45's exclusion and V44's
merge/search). Re-run the FULL pre-existing suite to confirm zero regressions.

### 4.2 Execute the redeploy yourself
Run:
```
docker compose build frontend
docker compose up -d frontend
docker compose up -d --force-recreate worker-general worker-webhooks beat backend
```
Verify live: the purge job's running configuration now genuinely shows 90 days (not just
committed in source); the date-range dropdown in the served frontend bundle reflects the
adjusted options (grep the actual served assets, not just timestamps); a live test
message matching the previously-missed pattern is now correctly detected.

---

## FINAL REPORT
- Confirm the purge job's real, live interval is now 90 days (with evidence, not just a
  claim), and state the decision made about story media/analysis retention alongside it.
- Confirm the date-range UI options now honestly reflect the real retention ceiling.
- Confirm the detection fix with the real previously-missed example now correctly
  caught, and confirm no new false positives on real non-product messages.
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- Confirm the redeploy was executed (not just recommended) and verified live.
- The list of pushed commits.

Then STOP and await review.