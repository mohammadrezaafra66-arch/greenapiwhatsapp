# V44 MASTER PROMPT — Afrakala WhatsApp Sender
## Verify/fix product-name merging in the top-products report + add search

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
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, through V43
(reporting date-range/limit expansion, both backend and frontend confirmed live and
verified against the served bundle) and V44's prerequisites.

TWO THINGS TO DO, in order:
1. VERIFY (don't assume) whether the "جدول محصولات پر تکرار" (top-products) report
   currently merges near-identical product-name mentions into one row, or whether it
   naively groups by exact string match — which would silently fragment the same real
   product into multiple rows whenever contacts phrase it slightly differently (spacing,
   punctuation, Latin vs Persian brand spelling, etc.), undercounting the true repeat
   frequency. Fix this if it's naively exact-match, reusing whatever normalization
   already exists in this codebase (e.g., V40's product_match/catalog-matching logic) for
   consistency — do not invent a second, divergent normalization scheme.
2. ADD a search box to the top-products report table so the user can filter by product
   name.

### NON-NEGOTIABLE GUARDRAILS
1. Reuse the existing top-products aggregation/endpoint — extend it, don't replace it or
   build a parallel one.
2. If normalization logic already exists elsewhere in this codebase for product
   matching (V40's product_match.py or similar), reuse that exact logic for grouping
   here too — don't write a second, different normalization rule that could disagree
   with it.
3. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
4. Commit + push each PART separately ("V44 PART N: ...").

### WORKFLOW PER PART
Read the actual current grouping/aggregation code and the actual current Reporting.jsx
first (don't assume) → extend/fix → write/extend tests using REAL example product-name
variants pulled from the live database (not synthetic examples) → run the FULL existing
test suite → verify zero regressions → commit + push → next PART.

---

## PART 1 — Investigate current product-name grouping

### 1.1 Investigate
- Read the exact current grouping/aggregation query behind the top-products report
  (e.g., `top_products_rows` / `product_reports.py`) and confirm precisely how it groups
  rows: exact `product_name` string match, or some normalization first?
- Pull real examples from the live database: find pairs or clusters of product-mention
  rows that a human would clearly recognize as the SAME product but that have slightly
  different `product_name` text (different spacing, punctuation, Persian/Latin digit or
  brand-name variants, etc.). Report several real examples.
- Confirm whether these real near-duplicate examples currently appear as SEPARATE rows
  in the report (undercounting) or are correctly merged into one row today.

### 1.2 Tests
A test capturing the real-world near-duplicate examples found in 1.1 (as fixtures, not
invented ones) asserts the CURRENT behavior precisely (documenting the actual bug/gap if
one exists, or documenting correct existing behavior if it turns out fine).
Commit + push "V44 PART 1: investigate current product-name grouping behavior (findings only)".

---

## PART 2 — Fix grouping if it's naively exact-match

### 2.1 Fix (only if PART 1 found a real gap)
- If PART 1 confirms near-duplicate real products are being split into separate rows,
  add a normalization step before grouping — reusing any existing normalization utility
  in this codebase (check product_match.py / catalog-matching logic first) rather than
  writing a new one. Reasonable normalization includes: trimming/collapsing whitespace,
  case-folding where applicable, and any existing Persian-digit/Latin-digit or common
  brand-alias handling already established elsewhere in this project.
- If PART 1 finds grouping is ALREADY correct (e.g., it already reuses a shared
  normalization/catalog-match step), do not change anything here — just confirm and
  report that no fix was needed, with the supporting evidence from PART 1.

### 2.2 Tests
The real near-duplicate examples from PART 1 now correctly merge into a single report
row with a combined mention_count (if a fix was needed); if no fix was needed, add a
regression test locking in the already-correct behavior using those same real examples
so it can't silently regress later. Run the FULL existing suite and confirm zero
regressions to unrelated report rows (a fix must not over-merge genuinely different
products).
Run full suite. Commit + push "V44 PART 2: fix/confirm product-name grouping for near-duplicate mentions".

---

## PART 3 — Add search to the top-products report table

### 3.1 Build
- Add a search input to the "جدول محصولات پر تکرار" tab on /reporting, letting the user
  filter the table by product name (substring match, case-insensitive, and ideally
  tolerant of the same normalization from PART 2 so a search for one phrasing of a
  product also finds rows written slightly differently).
- Decide, based on investigating the current data volume/architecture: filter
  server-side (add a `search` query param to the existing endpoint) if the table can
  hold up to 1000 rows per V43 (server-side is more scalable), or client-side over the
  already-fetched page if that's simpler and still performant — justify whichever choice
  is made in the report.
- The search should work together with the existing date-range, count-limit, and source
  filters from V40/V43 — not replace or conflict with them.

### 3.2 Tests
Searching for a product name (including a real near-duplicate example from PART 1/2)
correctly returns matching rows; searching for a term with no matches returns an empty,
clearly-labeled state (not an error); the search works correctly alongside the existing
date-range/limit/source filters together.
Run full suite (backend + frontend build/pure-module tests). Commit + push
"V44 PART 3: add search to the top-products report table".

---

## PART 4 — Final wiring + full regression pass

### 4.1 Tests
Full end-to-end simulation: seed real-world near-duplicate product mentions plus clearly
distinct products → confirm the report correctly merges the near-duplicates and keeps
distinct products separate → confirm search correctly finds a product across its
near-duplicate phrasings → confirm date-range/limit/source filters still work correctly
alongside search. Re-run the FULL pre-existing suite to confirm zero regressions.
Run full suite. Commit + push "V44 PART 4: final wiring + full regression pass".

---

## FINAL REPORT
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- PART 1's real findings: was grouping already correct, or was there a genuine gap —
  with the real example product names that proved it either way.
- PART 2: exactly what was fixed (if anything), and confirmation it doesn't over-merge
  genuinely different products.
- PART 3: confirm search works, and whether it's server-side or client-side and why.
- The list of pushed commits, and the redeploy reminder:
  "docker compose build frontend && docker compose up -d frontend" and
  "docker compose up -d --force-recreate worker-general worker-webhooks beat backend".

Then STOP and await review.