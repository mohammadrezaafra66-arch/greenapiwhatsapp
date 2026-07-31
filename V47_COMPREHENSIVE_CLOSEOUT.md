# V47 MASTER PROMPT — Afrakala WhatsApp Sender
## Comprehensive close-out: own-number cleanup + async story-analysis job + approved menu/sidebar reorganization

> MODE: FULLY AUTONOMOUS, RESUMABLE ACROSS SESSION LIMITS. Execute every PART end-to-end
> WITHOUT asking questions and WITHOUT waiting for approval. After EVERY PART: run the
> full existing test suite AND a self-check specific to that part (detailed per PART
> below); only advance once every check passes. Commit and push each PART separately.
> If you hit a usage/session limit mid-part, stop cleanly; on the next invocation, run
> "git log --oneline -25" AND "git status" first, and resume from the next incomplete
> PART rather than restarting or redoing already-committed work. Do not leave any part
> of this prompt undone — if something described below turns out to already be
> implemented from a prior session, VERIFY it thoroughly (don't just trust a claim) and
> move on; do not skip verification for anything.
>
> OUTPUT LANGUAGE: report to the user in English only, per this project's CLAUDE.md rule.
> All in-app UI strings stay Persian/RTL as always.

---

## 0. CONTEXT (read in full before starting)

Project: C:\Users\AFRA\Desktop\bots\claudegreenapi
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, through V45
(own-number exclusion + active-contacts harvesting).

This prompt closes out THREE outstanding threads in one pass:

**THREAD A — V45 leftover:** 2 historical `product_mention_logs` rows were found to
match a currently-listed own-number (out of ~1,370 total) and were reported but
deliberately not deleted, awaiting confirmation. Clean these up now.

**THREAD B — async story-analysis job.** Diagnosed root causes (do not re-diagnose,
build directly from these confirmed findings):
1. The "تحلیل همه استوری‌های امروز" button (`Statuses.jsx` → `analyzeToday()`) makes a
   single synchronous `axios` POST to `/statuses/analyze-today` with NO per-call timeout
   override, so it inherits the shared client's hardcoded `timeout: 30000`. The backend
   loops through every eligible story sequentially (real vision-API calls per image) and
   commits ONCE at the very end. On a day with a real backlog (confirmed: 636 stories
   received on one day, only 441 processed before something interrupted it), the browser
   aborts at 30s while the server may still be working — and if the request/worker is
   torn down mid-run, the single end-of-loop commit means the ENTIRE run's work is lost
   (not just the unfinished remainder).
2. The button only looks at stories received "today" (UTC midnight boundary) — a
   confirmed backlog of 195 un-analyzed stories from a PRIOR day is invisible to it and
   will never be picked up by clicking this button, no matter how many times it's
   clicked.
3. Of those 195, 68 are videos (no downloaded frame, vision has nothing to analyze) and
   127 are text-type stories (58 of which have literally empty `text_content`) — none of
   these ever get an analysis row created for them today, so they sit as "eligible"
   forever even after every image story has been cleared, and the eligible count can
   never reach a true zero.
4. This project ALREADY has an established pattern for exactly this situation elsewhere
   in the codebase (progress-polling on a background job — e.g. `pfpProgress`,
   `safeAddProgress`, `extractProgress`) — reuse that exact pattern, do not invent a new
   one. (General best practice, confirmed via research: dispatch a Celery task
   immediately, return a `task_id`, have the task call `self.update_state(...)` with
   progress as it works, and have the frontend poll a status endpoint — this project's
   own existing progress-task pattern already implements this correctly elsewhere.)

**THREAD C — approved menu/sidebar reorganization.** The user reviewed a standalone
research prototype (`ui-research/menu-prototype.html`) and approved the proposed
reorganization. Implement it FOR REAL in the actual application now — but the user has
explicitly and repeatedly stressed the single most important constraint: **nothing that
currently exists in the frontend may be lost, hidden, or become unreachable** — every
button, page, and route that exists today must still exist and be reachable after the
reorganization (regrouped/renamed is fine; disappearing is not). This must be verified
with an actual automated check, not just a visual reading.

The approved target structure (from the prototype, STEP 2 of the research):
- ⭐ میهم دراوم (pinned/favorites, simple and customizable if easy to do — otherwise a
  static pinned list is fine): Dashboard, Inbox, Campaigns, Send-queue, Protection.
- 📤 لاسرا و اهن‌یپمک: Campaigns (with Campaign ROI moved IN as an in-page tab, not a
  separate sidebar leaf), the group-send/collections items (DEDUPLICATED — `/wa-collections`
  currently appears twice under two different labels; keep one), Send-queue, Templates,
  Interactive buttons.
- 👥 نیبطاخم و نیرصاخم: Contacts, Contact-groups, WhatsApp groups, Blacklist, PLUS Active
  WhatsApp Contacts (moved here from Reports — it's a lead list, not a report).
- 💬 اهوگتفگ: Inbox, Message history, Auto-reply, Group monitoring, Calls (unchanged
  cluster, per the research finding it was already coherent).
- ✍️ اوتحم و یروتسا: Stories, Story schedule, Advertising links, Contact-card/location,
  Files.
- 📱 اهه‌رامش: Onboarding (new-number setup), WhatsApp accounts, Telegram accounts,
  Account scheduling, Partner management — "manage my lines" lifecycle only.
- 🛡️ یدودسمدض و تمالس (NEW group — split out of the old overloaded "Numbers" group):
  Protection & health, Smart warm-up, Team collaboration — "keep my lines alive."
- 📊 لیلحت و اهش‌رازگ: Daily report (with Best-send-hours and Emergency-numbers folded IN
  as in-page tabs, not separate sidebar leaves that were secretly aliasing the same
  route), Product tracking (top-repeated-products).
- ⚙️ تامیظنت: AI keys, AI settings, Own-numbers exclusion list, Group/channel join-links,
  Green API capabilities.

Specific known issues to fix as part of this reorg (confirmed by the research, not
assumptions):
- `/wa-collections` currently has TWO sidebar leaves pointing to it under different
  labels — collapse to one.
- Three leaves ("بهترین ساعت ارسال", "شماره‌های اضطراری", "بازده کمپین (ROI)") are
  "phantom" entries that just alias `/reporting` or `/campaigns` respectively — convert
  these into in-page tabs on their real parent page instead of separate misleading
  sidebar entries.

### NON-NEGOTIABLE GUARDRAILS
1. NEVER enable Green API polling. Webhook-only stays intact.
2. THREAD B: reuse the existing progress-task/polling pattern already in this codebase
   — do not build a second, different async-job mechanism.
3. THREAD C: this is a REGROUPING/renaming/deduplication of navigation ENTRIES to
   existing routes/pages — it is NOT a rewrite of any page's actual functionality.
   Do not delete, rewrite, or functionally change any existing page while moving its
   sidebar entry; only the navigation tree and route groupings change.
4. THREAD C is the highest-risk part of this prompt for accidentally losing something —
   build and run an explicit automated route/feature-inventory diff (before vs. after)
   as its own dedicated verification step; do not rely on manual visual review alone.
5. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
6. Commit + push each PART separately ("V47 PART N: ...").

### WORKFLOW PER PART
Investigate the actual current code first (don't assume) → implement → write/extend
tests → run the FULL existing test suite → run this PART's own specific self-check
(detailed below) → verify zero regressions → commit + push → next PART.

---

## PART 1 — THREAD A: clean up the 2 historical own-number rows

### 1.1 Verify then delete
- Re-query `product_mention_logs` for rows matching a currently-listed own-number core
  (reuse the exact matching logic already built in V45's report-side safety net).
  Confirm it's still exactly 2 rows (or report the current real count if it has changed).
- Delete these specific rows (only rows matching a currently-listed own number — nothing
  else). Log exactly which rows were deleted (id, product_name, phone) in the final
  report for auditability.

### 1.2 Self-check
Re-run the same query after deletion and confirm zero matching rows remain; confirm the
top-products report's total row/mention counts shift down by exactly the deleted rows'
contribution (no unrelated data affected).
Run full suite. Commit + push "V47 PART 1: clean up historical own-number report rows".

---

## PART 2 — THREAD B: convert story analysis to an async, resumable background job

### 2.1 Backend: async job + incremental progress
- Convert the `/statuses/analyze-today` endpoint (and the underlying analysis loop) to
  dispatch a Celery task immediately and return a `task_id`, reusing this project's
  EXISTING progress-task pattern (find and mirror `pfpProgress`/`safeAddProgress`/
  `extractProgress` exactly — same state-storage mechanism, same status-endpoint shape).
- The task must report incremental progress (e.g., `{done: N, total: M, skipped: K}`)
  via `self.update_state` (or this project's equivalent existing mechanism) as it works,
  not just a final result.
- Change the commit strategy from "one commit at the very end" to incremental commits
  (e.g., per small batch, mirroring the batching approach already used in the earlier
  bulk-reanalysis script) so a worker restart or cancellation loses at most one
  in-flight batch, never the whole run.

### 2.2 Backend: process the FULL backlog, not just "today"
- Change the eligibility query to include ALL un-analyzed stories regardless of when
  they were received (drop the "today only" UTC-midnight filter as the default scope).
  If a "today only" mode still has value, keep it as an explicit opt-in parameter, but
  the default/primary bulk action should clear the real backlog, matching what the user
  actually expects when they click "analyze everything."

### 2.3 Backend: give text-empty and video stories a terminal state
- For stories with `status_type` indicating video (no downloadable/analyzable frame) or
  text-type stories with empty/whitespace-only `text_content`: instead of leaving them
  permanently "eligible," create an analysis row marked with a clear terminal/skipped
  state (e.g., `analysis_type="skipped_no_content"` or similar — reuse existing enum
  patterns if any exist) so the eligible count can genuinely reach zero. This must NOT
  count as a "product analyzed" success in the summary — report it as its own distinct
  category (e.g., "skipped — no analyzable content") so the numbers stay honest.

### 2.4 Frontend: progress UI
- Replace the single synchronous await with: kick off the job, get a `task_id`
  immediately, then poll a status endpoint (reusing the existing progress-polling
  component pattern from `pfpProgress`/`safeAddProgress`/`extractProgress` — reuse the
  actual shared component/hook if one exists, don't build a parallel one) showing live
  "X / N تحلیل شد، Y رد شد (بدون محتوای قابل‌تحلیل)" progress, not a blocking spinner
  with a 30s cliff.

### 2.5 Self-check
Seed a scenario with more eligible stories than would fit in 30 seconds of real
processing time (or a mocked slow path) and confirm the endpoint returns a `task_id`
near-instantly (no 30s wait), progress updates are observable via the status endpoint
as the job runs, and the job survives a simulated mid-run interruption with only the
unfinished remainder lost (already-committed batches survive). Separately, confirm a
video-only and a text-empty story both end up in a terminal "skipped" state rather than
remaining eligible forever, and are excluded from future backlog runs. Confirm a
scenario with a genuine multi-day backlog (stories from more than one day) are ALL
processed by the default action, not just today's.
Run full suite (backend + frontend build/pure-module tests). Commit + push
"V47 PART 2: async, resumable, full-backlog story-analysis job with terminal states for empty/video stories".

---

## PART 3 — THREAD C, step 1: inventory the CURRENT navigation exhaustively (before touching anything)

### 3.1 Build an automated inventory
- Write a script/test that walks the CURRENT `Layout.jsx` (or wherever the nav tree
  lives) and the CURRENT `App.jsx` routes, and produces a complete, structured list of
  every distinct route/path currently reachable from the sidebar, plus every route
  defined in the router (to catch any route not currently in the sidebar too, exactly
  as the research step already did manually — now make it a repeatable, automated
  check). Save this as a baseline snapshot (e.g., a JSON/text fixture file) BEFORE any
  reorganization work begins.

### 3.2 Self-check
The baseline snapshot exists and lists all confirmed current routes/groups (cross-check
its count against the research report's finding of 34 distinct routes + the 3 phantom
aliases + the 1 duplicate, adjusting if the live count has changed since that report).
Commit + push "V47 PART 3: baseline navigation inventory snapshot (pre-reorg)".

---

## PART 4 — THREAD C, step 2: implement the approved reorganization

### 4.1 Restructure the navigation tree
- Implement the approved grouping from section 0 above in `Layout.jsx` (or wherever the
  nav tree lives): the new group labels/icons, the deduplicated `/wa-collections` entry,
  and the pinned/favorites area.
- Do NOT remove or rename any actual page/route/component — only change which sidebar
  group/label a route's entry appears under, and which routes get folded into in-page
  tabs (see 4.2).

### 4.2 Convert the 3 phantom-alias leaves into real in-page tabs
- "بهترین ساعت ارسال" and "شماره‌های اضطراری" currently alias `/reporting` — instead of
  separate misleading sidebar leaves, make them tabs INSIDE the reporting page (reusing
  whatever tab pattern the reporting page already uses for its other tabs, e.g. the
  top-products/product-tracking tabs already there).
- "بازده کمپین (ROI)" currently aliases `/campaigns` — make it a tab inside the
  campaigns page similarly.
- Remove the now-redundant separate sidebar leaves for these three, since their content
  is now reachable as tabs on their real parent page.

### 4.3 Self-check — the critical "nothing lost" verification
- Re-run PART 3's inventory script against the NEW navigation tree and NEW route
  structure, and produce a structured DIFF against the PART 3.1 baseline snapshot.
- Assert programmatically: every route present in the baseline is STILL present and
  reachable in the new structure (whether directly in the sidebar, inside a pinned
  area, or as an in-page tab on its real parent) — a route disappearing entirely is a
  hard test failure, not just a warning.
- The only INTENTIONAL differences allowed by this diff are: the `/wa-collections`
  duplicate removed (now appears once), and the 3 phantom-alias sidebar leaves removed
  (their content now reachable via in-page tabs instead — confirm the diff script
  accounts for this correctly, not as a false "lost route").
- Manually re-verify by reading the new Layout.jsx/App.jsx alongside the diff output —
  do not rely solely on the automated check; explicitly cross-check every group's item
  list against the approved structure in section 0.

### 4.4 Tests
The automated diff test from 4.3 passes (zero unintended losses); a rendering/pure-
module test confirms every new group renders its expected items; the deduplicated
`/wa-collections` entry and the two converted-to-tabs pages (reporting, campaigns) all
render their new tabs correctly with the moved content still functioning exactly as
before (only its location changed).
Run full suite (backend + frontend build/pure-module tests). Commit + push
"V47 PART 4: implement approved menu/sidebar reorganization with automated nothing-lost verification".

---

## PART 5 — Final wiring + full regression pass across all three threads

### 5.1 Tests
Full end-to-end simulation covering all three threads together: the 2 historical rows
are gone and the report total reflects it; a simulated large story backlog is fully
processed via the new async job (spanning multiple days, including video/text-empty
stories reaching a terminal skipped state, with live progress observable); the
reorganized navigation renders correctly with zero lost routes per the automated diff.
Re-run the FULL pre-existing suite (V17 through V45) to confirm zero regressions
anywhere in the whole application.
Run full suite. Commit + push "V47 PART 5: final wiring + full regression pass".

---

## PART 6 — Redeploy (do this yourself, do not just remind the user)

### 6.1 Execute the redeploy
Run, in order:
```
docker compose build frontend
docker compose up -d frontend
docker compose up -d --force-recreate worker-general worker-webhooks beat backend
```

### 6.2 Self-check — verify live, with real evidence, not just container-up status
- Confirm all containers report healthy/Up.
- Confirm the NEW frontend bundle is actually being served (grep the served JS assets
  for a distinctive new-structure string, e.g. one of the new group labels, and confirm
  it's present — do not rely on build timestamps alone, given this project's own history
  of a stale-frontend-image incident earlier).
- Confirm the async story-analysis endpoint now returns a `task_id` immediately (real
  HTTP call) rather than blocking.
- Confirm the 2 historical own-number rows are genuinely gone from the live report
  endpoint's output (real HTTP call).

---

## FINAL REPORT
- Confirm THREAD A: exactly which rows were deleted, and the live report's corrected
  totals.
- Confirm THREAD B: the async job works end-to-end with real evidence (task_id
  returned instantly, progress observable, full backlog processed, text/video stories
  reach a terminal skipped state) — and give the current real eligible-count (should be
  0, or explain precisely what remains and why).
- Confirm THREAD C: the full before/after route inventory diff, explicitly listing that
  zero routes were lost (only the intentional dedup + tab-conversions occurred), plus
  screenshotless textual confirmation the new bundle is live and serving the new
  structure.
- Test count before -> after, per-PART deltas, "zero regressions" confirmed for the
  whole pre-existing suite.
- Confirm: polling never enabled; no unrelated code touched; guardrails held throughout.
- The full list of pushed commits across all parts.

Then STOP. Nothing should remain undone from this prompt when this report is produced.