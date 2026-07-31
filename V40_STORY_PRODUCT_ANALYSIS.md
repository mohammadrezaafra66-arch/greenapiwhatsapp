# V40 MASTER PROMPT — Afrakala WhatsApp Sender
## Story product analysis: new tab inside Stories, AI text/image detection, feeds the existing product report, per-contact trend, catalog-spotted alert

> MODE: FULLY AUTONOMOUS, RESUMABLE ACROSS SESSION LIMITS. Execute every PART end-to-end
> WITHOUT asking questions and WITHOUT waiting for approval. After each PART: run a heavy
> test suite and verify it works; only advance once every test passes. Commit and push
> each PART separately. If you hit a usage/session limit mid-part, stop cleanly; on the
> next invocation, run `git log --oneline -15` first and resume from the next incomplete
> PART rather than restarting.

> OUTPUT LANGUAGE: report to the user in English only, per the project's existing
> CLAUDE.md rule. All in-app UI strings stay Persian/RTL as always — this rule is about
> your reports/commits/summaries to the user, not the product itself.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi` (GitHub:
`mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main, V17 through V39 merged
(mesh, V27 anti-ban, Telegram, V28-V39 Team Collaboration incl. the universal 24h
connect-cooldown and the hard 14-day sender-eligibility gate). Reporting page at
`/reporting` already has a working "جدول محصولات پرتکرار" (frequently-repeated products)
table, populated from `ProductMentionLog` rows written by `detect_product_mentions()` in
`webhook.py`'s incoming-message handler (PV + group chats), using the existing product
catalog (`price_service.get_products`, backed by the Supabase feed) only as a match
reference — non-catalog products are still logged and shown as "خارج از دستیار."

**This prompt adds Story (status) product detection as a first-class source feeding the
SAME reporting pipeline** — built as an extension of the existing "Stories received" page
(the tab the user refers to as "استوری‌های دریافتی"), not a separate/parallel page.

**User's confirmed scope (do exactly this, nothing more for this pass):**
1. Price extraction is explicitly OUT of scope for this pass — do not attempt to parse or
   store prices from story text/images.
2. Per-contact advertising-trend-over-time IS wanted — a view showing, for a given real
   contact, every product they've been observed advertising over time (across sources),
   so the user can see repeat-advertising patterns.
3. A "catalog product spotted" alert IS wanted, in a DEFERRED, price-free form: since price
   extraction is out of scope now, this pass builds "alert when a catalog (in_assistant)
   product is spotted being advertised by an outside contact" — NOT a price-comparison
   alert (that upgrade is explicitly future work once price extraction exists later; do
   not fake or approximate a price comparison without real price data).
4. CRITICAL requirement, called out by the user as very important: every product detected
   from a Story MUST flow into the EXISTING "جدول محصولات پرتکرار" table on `/reporting` —
   extend the existing `ProductMentionLog`-based pipeline with a `source` field
   (pv/group/status), do not build a second, separate product-mentions table.

### NON-NEGOTIABLE GUARDRAILS
1. NEVER enable Green API polling. Webhook-only stays intact.
2. Do NOT touch ngrok/webhook wiring for anything unrelated to statuses. Do not weaken any
   existing V27/V39 safety gate.
3. Reuse existing capability — do not reimplement: reuse `detect_product_mentions()` for
   text, the existing multi-provider AI key pool for image/vision analysis, the existing
   Shamsi date utility, and the existing `ProductMentionLog`/reporting pipeline.
4. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
5. Commit + push each PART separately (`V40 PART N: ...`).

### WORKFLOW PER PART
Investigate the ACTUAL current code first (the existing Stories-received feature — which
webhook event delivers statuses, where they're currently stored/displayed; the existing
`ProductMentionLog` model and `/reporting` frequently-repeated-products query; the existing
AI key pool's vision/image capability) before writing anything → extend, don't duplicate →
write/extend tests → run the FULL existing test suite → verify zero regressions → commit +
push → next PART.

---

## PART 1 — Persist story media at receipt time (critical prerequisite)

**Why this is PART 1:** WhatsApp statuses expire ~24h after posting. If media is only
referenced by a URL/pointer rather than downloaded, later analysis (especially the daily
bulk-analyze feature in PART 3) will fail once a story expires. This must be solved before
any analysis feature is built on top.

### 1.1 Investigate + fix
- Find the exact current webhook handling for incoming statuses (likely a status-specific
  event type, separate from `incomingMessageReceived`). Confirm whether image/media
  content is currently downloaded and persisted locally, or only referenced by a
  possibly-expiring URL.
- If not already persisted: on receipt, download the story's media (image) and save it to
  local storage (same convention as any other locally-stored media in this project, e.g.
  `CampaignMediaSend` or similar), storing the local path/reference in the story's DB row.
- Ensure text-only statuses continue to work as before (no media to persist).

### 1.2 Tests
A story with an image is received via webhook → its media is downloaded and persisted
locally at receipt time, with the local path recorded; a text-only story is unaffected.
Run full suite. Commit + push `V40 PART 1: persist story media at receipt time`.

---

## PART 2 — Story product-analysis data model + archive (analyze once, cache result)

### 2.1 Schema
- New table, e.g. `story_product_analysis`: `id`, `story_id` (FK to the existing
  story/status model), `analyzed_at`, `analysis_type` (text/image), `detected_product_name`
  (nullable), `matched_product_id` (nullable, FK to the catalog if matched),
  `in_assistant` (bool), `ai_confidence` (nullable float), `raw_ai_note` (nullable text,
  short), `created_at`.
- A story is analyzed AT MOST ONCE — if `story_product_analysis` already has a row for a
  given `story_id`, re-analysis is a no-op (return the cached result), never re-calls the
  AI. This is a hard cost-control rule per the user's explicit requirement.

### 2.2 Tests
Analyzing the same story twice only calls the AI/OCR path once; the second call returns
the cached row. Run full suite. Commit + push `V40 PART 2: story analysis schema + one-time-analysis archive`.

---

## PART 3 — Analysis logic: text + image, manual per-story button, bulk daily button

### 3.1 Text analysis
- For a text story: reuse the EXISTING `detect_product_mentions()` (do not reimplement),
  same catalog-matching + non-catalog extraction logic already used for PV/group messages.

### 3.2 Image analysis
- For an image story: use the project's EXISTING multi-provider AI key pool (whichever of
  OpenAI/Gemini/DeepSeek is already wired for this project and supports vision/image
  input) to extract any visible product name/description from the image, then run the
  same catalog-matching logic against it. If no AI provider in the pool currently supports
  vision, investigate and use the best available option, documenting the choice.
- Store `ai_confidence` if the provider returns one; otherwise a reasonable default/omit.

### 3.3 Manual per-story trigger
- Add a "تحلیل با هوش مصنوعی" button next to each story in the existing Stories-received
  list. Clicking it runs the appropriate (text or image) analysis for THAT story only, using
  the persisted local media from PART 1, and saves the result (PART 2's archive).

### 3.4 Bulk daily trigger
- Add a "تحلیل همه استوری‌های امروز" button (e.g. at the top of the Stories page). This
  analyzes every NOT-yet-analyzed story from today only, reusing the same per-story
  analysis function (no duplicated logic) and reports a short summary (X stories analyzed,
  Y products found, Z new senders/products not in catalog).

### 3.5 Tests
A text story is analyzed correctly (reuses the existing detector); an image story is
analyzed via the AI vision path and matched/unmatched correctly; the manual button
triggers analysis for one story only; the bulk button analyzes only today's unanalyzed
stories and produces a correct summary; re-running either never re-analyzes an
already-analyzed story (ties to PART 2's cache).
Run full suite. Commit + push `V40 PART 3: text + image story analysis, manual + bulk triggers`.

---

## PART 4 — New tab inside the Stories page: "تحلیل محصولات استوری‌ها"

### 4.1 UI
- Add a new tab alongside the existing "استوری‌های دریافتی" tab (same page, not a separate
  route), showing a table with exactly these columns: همکار/مخاطب (contact name), شماره/
  اکانت (phone), متن استاتوس (status text, if any), عکس/لینک استاتوس (thumbnail of the
  PERSISTED local image from PART 1 — never a possibly-expired original WhatsApp link),
  محصول تشخیص‌داده‌شده (detected product), برچسب در دستیار / خارج از دستیار (colored
  badge — green if `in_assistant`, orange/yellow if not), میزان اطمینان (AI confidence, if
  available), تاریخ و ساعت (Shamsi).
- Each row shows the small thumbnail with a caption like «تشخیص AI: <product name>»
  underneath, exactly as the user described.

### 4.2 Tests
The new tab renders correctly with seeded analysis data; the in-assistant/outside badge
colors match the `in_assistant` flag; thumbnails resolve to the locally-persisted image
path, not an external/expiring URL.
Run full suite (backend) + frontend build/pure-module tests. Commit + push
`V40 PART 4: "تحلیل محصولات استوری‌ها" tab in the Stories page`.

---

## PART 5 — Feed into the existing product report with a `source` field

### 5.1 Extend, don't duplicate
- Add a `source` field to the EXISTING `ProductMentionLog` model (values: `pv`, `group`,
  `status`) if it doesn't already have an equivalent field — investigate first, don't
  assume. Backfill existing rows as `pv`/`group` appropriately based on where they
  actually came from (investigate the existing write path to determine this correctly);
  never leave existing rows with an ambiguous/null source if a real value is derivable.
- Every story analysis that detects a product (PART 3) MUST write a
  `ProductMentionLog` row (or update repeat-counts on an existing matching row, following
  whatever aggregation the existing `/reporting` frequently-repeated-products query
  already does) with `source='status'`, so it appears in the SAME table already shown at
  `/reporting`'s "جدول محصولات پرتکرار" tab — not a second, separate table.

### 5.2 UI
- Add a "منبع" (source) column/filter to the existing frequently-repeated-products report
  table so the user can see/filter whether a product's mentions came from pv, group, or
  status.

### 5.3 Tests
A story-detected product correctly appears in the existing `/reporting` frequently-
repeated-products query with `source='status'`; filtering by source works; existing pv/
group rows are unaffected and correctly retain/receive their own source values.
Run full suite. Commit + push `V40 PART 5: story-detected products feed the existing report with source tagging`.

---

## PART 6 — Per-contact advertising trend over time

### 6.1 View
- Given a contact (identified by phone, unified across pv/group/status sources), provide a
  chronological view of every product they've been observed advertising over time (date,
  source, product name, in-assistant flag), plus a simple per-product repeat-count summary
  for that contact (e.g., "5 times in the last 2 weeks: Product X").
- Reasonable integration point: a drill-down from the existing "مشاهده فروشندگان اخیر"
  button already on the frequently-repeated-products table (investigate its current
  behavior first), or a new per-contact detail view reachable from any product-mention row
  — choose whichever fits the existing UI most naturally, don't build a disconnected page.

### 6.2 Tests
Given a contact with multiple mentions across pv/group/status over time, the trend view
correctly lists them chronologically with correct per-product repeat counts.
Run full suite. Commit + push `V40 PART 6: per-contact advertising trend over time`.

---

## PART 7 — Catalog-product-spotted alert (price comparison explicitly deferred)

### 7.1 Alert logic
- When a story (or, for consistency, any source — investigate whether this should apply
  to pv/group too or just stories; default to ALL sources since the underlying detection
  is shared, unless that conflicts with existing behavior) reveals a catalog
  (`in_assistant=True`) product being advertised by a contact who is NOT one of our own
  accounts, raise an admin alert/notification (reuse the existing alert/notification
  mechanism already used elsewhere in this project, e.g. V26's group-forbidden-word alert
  pattern — investigate and reuse its delivery mechanism, don't build a new one).
- Explicitly do NOT attempt any price comparison — there is no price data in this pass.
  Document clearly in code/comments that this is a "spotted" alert only, and that a future
  pass (once price extraction exists) should upgrade this to compare prices and alert only
  on undercutting, not on every sighting.

### 7.2 Tests
A catalog product observed being advertised by an outside contact raises exactly one
alert; a non-catalog product does not; re-observing the same already-alerted mention does
not spam a duplicate alert (reasonable dedup, e.g. one alert per (contact, product) per
day — choose a sensible window and document it).
Run full suite. Commit + push `V40 PART 7: catalog-product-spotted alert (price-free version)`.

---

## PART 8 — Final wiring + full regression pass

### 8.1 Wiring
- Confirm the full pipeline end-to-end: a story arrives → media persisted (PART 1) →
  manually or in bulk analyzed (PART 2/3) → shown in the new Stories tab (PART 4) → feeds
  the existing report with correct source tagging (PART 5) → contributes to the per-contact
  trend view (PART 6) → triggers the catalog-spotted alert when applicable (PART 7).

### 8.2 Tests
Full end-to-end simulation covering the whole pipeline above. Re-run the FULL pre-existing
suite (V17-V39) to confirm zero regressions.
Run full suite. Commit + push `V40 PART 8: final wiring + full regression pass`.

---

## FINAL REPORT
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- Confirm: story media is persisted at receipt time (never relies on a possibly-expired
  WhatsApp story URL for later analysis).
- Confirm: analysis is one-time/cached per story (cost control).
- Confirm: story-detected products appear correctly in the EXISTING `/reporting`
  frequently-repeated-products table with proper source tagging — not a separate table.
- Confirm: the per-contact trend view and the catalog-spotted alert both work, with the
  alert explicitly documented as price-free/deferred for now.
- Confirm: polling never enabled; ngrok/webhook untouched elsewhere; no existing V27/V39
  gate weakened.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
This feature turns story-watching from a manual, one-off glance into a structured,
queryable business-intelligence source that shares the same report the rest of the
project already uses. The price-comparison alert is intentionally deferred rather than
approximated, since a fake/estimated price comparison would be worse than none.