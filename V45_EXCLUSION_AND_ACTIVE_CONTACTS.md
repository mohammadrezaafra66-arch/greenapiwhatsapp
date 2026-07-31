# V45 MASTER PROMPT — Afrakala WhatsApp Sender
## Exclude our own numbers from product detection + harvest an active-contacts list

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
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, through V44
(product-name merging + search in the top-products report).

TWO SEPARATE (but related) requirements:

1. EXCLUDE OUR OWN NUMBERS FROM PRODUCT DETECTION ENTIRELY. There is a set of phone
   numbers that belong to this business itself (our own accounts/lines). Content from
   these numbers — across every source (PV, group, channel/کانال, forum/انجمن, broadcast
   list/لیست انتشار, and WhatsApp Status/story) — must NEVER be counted as a product
   mention in the "پرتکرار محصولات" report, because it's our own promotional content, not
   real competitor/customer market signal. Just as important: content from these numbers
   must NEVER consume AI tokens for analysis in the first place — the exclusion must
   happen BEFORE any detection/analysis call is made (especially the costly vision
   analysis for stories), not just as an after-the-fact filter on the report.

2. HARVEST AN "ACTIVE WHATSAPP CONTACTS" LIST. Build a mechanism that collects every
   DISTINCT phone number observed being active on WhatsApp — posting a Status/story, or
   writing in a group/channel/forum/broadcast-list message — into a dedicated contacts
   list/table ("مخاطبین فعال واتساپ"), for lead-generation purposes. Each number must be
   stored EXACTLY ONCE (deduplicated), with as complete information as is actually
   available (display name/push name, first-seen date, which source type it was first
   seen through, etc.), and the list must show a sequential row number (۱، ۲، ۳...). This
   list should also respect requirement 1 — our own numbers must never appear in it
   either.

### NON-NEGOTIABLE GUARDRAILS
1. NEVER enable Green API polling. Webhook-only stays intact.
2. Reuse the existing product-detection pipeline (product_match.py, the story-analysis
   pipeline from V40) — extend it with an early exclusion check, don't fork a parallel
   detection system.
3. The exclusion check must run BEFORE any AI/vision call — confirm this explicitly with
   a test (an excluded number's story/message must result in ZERO AI calls, not just a
   discarded result after a call was already made).
4. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
5. Commit + push each PART separately ("V45 PART N: ...").

### WORKFLOW PER PART
Read the actual current webhook/detection entry points first (message handler in
webhook.py, story analysis trigger from V40) → add the exclusion check at the earliest
possible point in each → write/extend tests → run the FULL existing test suite → verify
zero regressions → commit + push → next PART.

---

## PART 1 — Maintain an "our own numbers" exclusion list

### 1.1 Data model + management UI
- Add a simple table (e.g. `own_number_exclusions`): phone number (normalized, reuse
  existing phone-normalization utilities already in this codebase — do not write a new
  one), optional label/note, added_at.
- Add a small management UI (a new settings sub-page, or a section under an existing
  relevant settings page — investigate current settings page structure and place it
  naturally) to add/remove numbers from this list, showing the current list clearly.
- Pre-seed this list with the phone numbers of all currently-connected Green API
  instances in this system (since those are obviously our own numbers) — investigate the
  accounts table for this and add them automatically as a sensible default, while still
  allowing the user to add further numbers (e.g., personal/other business lines not
  connected as Green API instances) manually.

### 1.2 Tests
Adding/removing a number via the API works correctly; the pre-seed correctly populates
from currently-connected instances without duplicating; normalization correctly matches
equivalent phone formats (with/without country code, etc.) reusing existing utilities.
Run full suite. Commit + push "V45 PART 1: own-number exclusion list + management UI".

---

## PART 2 — Wire the exclusion into detection BEFORE any AI call, for every source

### 2.1 Message-based detection (PV, group, channel, forum, broadcast list)
- In the webhook handler that currently calls `detect_product_mentions` for incoming
  messages, add an early check: if the sender's phone number is in the exclusion list
  from PART 1, skip detection entirely for that message — do not call
  `detect_product_mentions` at all, and do not write any `ProductMentionLog` row.

### 2.2 Story-based detection (the costly vision path from V40)
- In the story analysis trigger (both the per-story button and the bulk "analyze all
  today" action), add the SAME early check: if the story's poster's phone number is in
  the exclusion list, skip analysis entirely — never call the vision/AI path for it, and
  never create a `story_product_analysis` row that would later feed the report. Mark it
  clearly as "excluded — own number" if the UI needs to reflect why it was skipped,
  rather than leaving it looking like an unprocessed/pending story forever.

### 2.3 Report-side safety net (defense in depth)
- Even though 2.1/2.2 should prevent any new rows from these numbers, add a filter in the
  top-products report query itself excluding any `ProductMentionLog` row whose sender
  phone is in the exclusion list — this protects against any legacy/pre-existing rows
  from before this fix, and against any future code path that might bypass the earlier
  checks.
- Report how many EXISTING rows (if any) are from currently-listed own-numbers, so the
  user can decide separately whether to clean up historical data (do not delete anything
  yourself without being asked — just report the count).

### 2.4 Tests
A message/story from an excluded number results in ZERO detection-function/AI calls
(assert this directly, e.g. via a call-count spy) and creates no log rows; a message/
story from a non-excluded number behaves exactly as before (no regression); the report
query correctly filters out any pre-existing rows from excluded numbers too.
Run full suite. Commit + push "V45 PART 2: wire own-number exclusion before any AI call, all sources".

---

## PART 3 — Active WhatsApp Contacts harvesting list

### 3.1 Data model
- Add a table (e.g. `active_whatsapp_contacts`): phone number (normalized, UNIQUE
  constraint so a number can never be stored twice), display/push name (nullable, best
  available), first_seen_at, first_seen_source (status/group/channel/forum/broadcast —
  whichever it was first observed through), last_seen_at (updated on later sightings).

### 3.2 Harvesting logic
- Wherever a story is observed (from V40's story reception) or a group/channel/forum/
  broadcast-list message is received, after confirming the sender is NOT in the PART 1
  exclusion list, upsert their phone number into this table: insert if new (with
  first_seen fields), or just update last_seen_at if already present — never create a
  duplicate row for the same number.
- This applies across ALL the mentioned source types (status, group, channel, forum,
  broadcast list) — investigate how each of these is currently distinguished in this
  codebase's data model (the `source`/chat-type handling already established from V40)
  and reuse that distinction rather than inventing new categories.

### 3.3 UI
- Add a new page/section «مخاطبین فعال واتساپ» listing every harvested contact, showing a
  sequential row number, phone, name (or "—" if unknown), first-seen date (Shamsi) and
  source, and last-seen date. Support the existing Excel-export pattern already used
  elsewhere in this project's reporting pages, if reasonable to reuse here too.

### 3.4 Tests
A new number seen for the first time creates exactly one row; the SAME number seen again
later updates last_seen_at without creating a duplicate row; an excluded (own) number is
never harvested into this list; the sequential row numbering displays correctly.
Run full suite (backend + frontend build/pure-module tests). Commit + push
"V45 PART 3: active WhatsApp contacts harvesting list".

---

## PART 4 — Final wiring + full regression pass

### 4.1 Tests
Full end-to-end simulation: a message/story from an excluded own-number triggers zero AI
calls, zero product-mention rows, and is not harvested into the active-contacts list; a
message/story from a genuine outside number is correctly detected/counted AND harvested
into the active-contacts list (deduplicated across repeated sightings). Re-run the FULL
pre-existing suite to confirm zero regressions.
Run full suite. Commit + push "V45 PART 4: final wiring + full regression pass".

---

## FINAL REPORT
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- The current exclusion list (pre-seeded numbers + any notes), and how to manage it.
- Confirm: zero AI calls are made for excluded numbers (with direct evidence, e.g. a
  call-count assertion, not just a claim).
- How many pre-existing report rows (if any) were found to already be from excluded
  numbers — reported, not deleted, unless the user asks for cleanup separately.
- Confirm the active-contacts list correctly deduplicates and excludes our own numbers.
- The list of pushed commits, and the redeploy reminder:
  "docker compose build frontend && docker compose up -d frontend" and
  "docker compose up -d --force-recreate worker-general worker-webhooks beat backend".

Then STOP and await review.