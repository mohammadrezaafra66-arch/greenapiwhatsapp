# V43 MASTER PROMPT — Afrakala WhatsApp Sender
## Expand the reporting page's date-range and product-count filters

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
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, through V42
and V41 Path B merged. The "جدول محصولات پر تکرار" (frequently-repeated-products) tab on
/reporting currently has, per the live UI: a date-range dropdown (currently limited
options, e.g. 30 days) and a product-count/limit dropdown (currently 50 / 100 / 150).
This prompt expands BOTH so the user has real flexibility.

### NON-NEGOTIABLE GUARDRAILS
1. Reuse the existing /reporting "top-products" endpoint and its existing `days` and
   `limit` query parameters — do not build a new endpoint or duplicate logic.
2. Do not change the existing default values (whatever the page currently loads with by
   default should stay the default) — only ADD more selectable options.
3. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
4. Commit + push each PART separately ("V43 PART N: ...").

### WORKFLOW PER PART
Read the actual current Reporting.jsx (frontend) and the actual current top-products
endpoint (backend) first — confirm the exact current option lists and query-param
handling before changing anything → extend → write/extend tests → run the FULL existing
test suite → verify zero regressions → commit + push → next PART.

---

## PART 1 — Expand the date-range dropdown

### 1.1 Investigate
- Read the current date-range dropdown's options and how the selected value maps to the
  `days` query parameter sent to the backend endpoint.

### 1.2 Expand
- Add a wider, sensible spread of options so the user can pick genuinely different
  windows, for example (adjust to fit naturally with whatever exists today, keep them in
  ascending order): 7 days, 14 days, 30 days (existing), 60 days, 90 days, 180 days,
  365 days, and an "همه‌ی زمان‌ها" (all time) option if the backend can reasonably support
  an unbounded/very large window without breaking.
- Confirm the backend's `days` handling (or an "all time" sentinel value) works correctly
  for every new option, including the largest one, without timing out or erroring — test
  this against real data volumes already in the database.

### 1.3 Tests
Each new date-range option produces the correct `days` value sent to the backend; the
backend correctly returns data for each window size, including the largest/"all time"
option, without error. The previously-existing options and default behavior are
unchanged (regression-checked).
Run full suite. Commit + push "V43 PART 1: expand the reporting date-range options".

---

## PART 2 — Expand the product-count limit dropdown up to 1000

### 2.1 Investigate
- Read the current count/limit dropdown's options (currently 50/100/150) and how the
  selected value maps to the `limit` query parameter.

### 2.2 Expand
- Add options in roughly 100-unit steps above the existing 150, up to a maximum of 1000:
  e.g. 150 (existing), 200, 300, 400, 500, 600, 700, 800, 900, 1000. Keep the existing
  50/100/150 options too — this is purely additive.
- Confirm the backend endpoint and the export ("خروجی اکسل") path both handle a limit as
  high as 1000 correctly and performantly (check the actual query — add pagination/index
  support if a naive query would be too slow at 1000 rows; investigate before assuming it
  just works).

### 2.3 Tests
Each new limit option is sent correctly and the backend returns up to that many rows
(or fewer if fewer exist) without error, including at the max of 1000; the Excel export
path also works correctly at the higher limits; existing lower-limit behavior is
unchanged (regression-checked).
Run full suite. Commit + push "V43 PART 2: expand the reporting product-count limit up to 1000".

---

## PART 3 — Final wiring + full regression pass

### 3.1 Tests
Full end-to-end simulation: select the largest date range + the max 1000-product limit
together and confirm the page loads correctly with real data, including the source
filter/tags from V40 still working correctly alongside these new options. Re-run the
FULL pre-existing suite to confirm zero regressions.
Run full suite (backend + frontend build/pure-module tests). Commit + push
"V43 PART 3: final wiring + full regression pass".

---

## FINAL REPORT
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- The exact final list of date-range options and count-limit options now available.
- Confirm: existing defaults unchanged; the V40 source filter/tagging still works
  correctly with the new options.
- The list of pushed commits, and the redeploy reminder:
  "docker compose build frontend && docker compose up -d frontend" and
  "docker compose up -d --force-recreate worker-general worker-webhooks beat backend".

Then STOP and await review.