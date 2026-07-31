# AFRAKALA ASSISTANT SYNC — market-intelligence page catch-up
## Bring the "پرتکرار محصولات" display at /pricing/market-intelligence fully up to date with the WhatsApp platform's current reporting API

> MODE: FULLY AUTONOMOUS. Execute start to finish WITHOUT asking any question and
> WITHOUT waiting for approval. If you hit a usage/session limit mid-task, stop cleanly;
> on the next invocation, run "git log --oneline -20" AND "git status" first, and resume
> from the next incomplete step.
>
> IMPORTANT: run this in the "دستیار هوشمند افراکالا" project
> (working directory D:\AfraKalaTest\app, docker-compose project "afrakala-lan",
> service "web", published on host port 3100). This is a DIFFERENT, SEPARATE repository
> from the WhatsApp automation platform (claudegreenapi) — do NOT open or modify the
> claudegreenapi repo in this session; only READ its live API responses over HTTP as
> needed for investigation.

---

## 0. CONTEXT (read first)

This project ("دستیار هوشمند افراکالا") already has an existing, working integration
that displays an overview of the WhatsApp platform's "جدول محصولات پر تکرار"
(frequently-repeated-products) report on the page /pricing/market-intelligence, inside a
scrollable card/table on that page. This integration reads (directly or via a small
proxy — investigate which) from the sibling WhatsApp automation platform's live API,
reachable at its reporting endpoint (base likely http://192.168.170.8:8002 or similar —
confirm the ACTUAL URL this project currently uses by reading its own existing
integration code, do not guess).

THE PROBLEM: this integration was built BEFORE several rounds of changes on the
WhatsApp-platform side, and has not been updated since. It is now stale in (at least)
these ways:
1. The WhatsApp platform's report now tags every product mention with a `source`
   (whether it came from a private WhatsApp message, a group message, or a WhatsApp
   Status/story) and includes products detected from Status/story images specifically —
   this project's display may not show or account for this `source` information at all.
2. The WhatsApp platform's report now also supports a "catalog-product-spotted" concept
   (a product from our own catalog seen being advertised by an outside contact) — check
   whether this project should also reflect that, if the report endpoint surfaces it.
3. The WhatsApp platform's reporting page just had its date-range and product-count
   limit options SIGNIFICANTLY expanded (date range now offers many more windows up to
   "all time"; product-count limit now goes up to 1000, in roughly 100-unit steps above
   the previous max of 150). If this project exposes its own range/count controls
   mirroring the WhatsApp platform's, they need the same expanded options; if it just
   displays a fixed pull, confirm what parameters it currently requests and whether it
   should request a larger/more current window now.

YOUR TASK: investigate this project's ACTUAL current integration code, investigate the
WhatsApp platform's ACTUAL current live API response shape (by making real HTTP requests
to it, not by guessing), and update this project's display/fetch logic so it correctly
and fully reflects everything the WhatsApp platform's report now provides — without
breaking anything else in this project.

### NON-NEGOTIABLE GUARDRAILS
1. Do NOT modify the claudegreenapi (WhatsApp platform) repository in any way. Read-only
   HTTP calls to its live API are fine; do not open its source code or change its files.
2. Do NOT change this project's own Supabase schema/data model unless genuinely required
   to store/display the new `source` information — if a schema change is needed, make it
   additive (new nullable column/field) and reversible, never destructive.
3. Preserve everything else on /pricing/market-intelligence and elsewhere in this
   project that isn't part of this specific sync — this is a targeted update, not a
   rebuild.
4. All UI strings in this project's own established language/style convention (match
   whatever the existing page already uses — investigate and follow it, don't assume
   Persian/RTL conventions from a different project apply here if this project does
   things differently).
5. Commit + push each step separately with clear messages.

### WORKFLOW
Investigate this project's actual current code AND the WhatsApp platform's actual
current live API response FIRST — do not assume either one without verifying → fix/
extend → test using whatever this project's existing test/build tooling is → verify
zero regressions to anything unrelated → commit + push → next step.

---

## STEP 1 — Investigate both sides

### 1.1 This project's current integration
- Find the exact code path that fetches and renders the market-intelligence product
  table on /pricing/market-intelligence (the specific scrollable card/table area on that
  page). Identify: the exact URL/endpoint it currently calls on the WhatsApp platform,
  what query parameters it sends (if any), and exactly what fields of the response it
  currently reads/displays and which it silently ignores or doesn't expect at all.

### 1.2 The WhatsApp platform's current live API
- Make real HTTP GET requests to the WhatsApp platform's reporting endpoint (whatever
  base URL STEP 1.1 revealed this project actually uses) with a few different parameter
  combinations, and inspect the FULL current response shape — specifically confirm: the
  `source` field/array per product (values covering private-message, group-message, and
  status/story), any catalog-match/"outside assistant" indicator field, the available
  `days` and `limit` parameter ranges (per the just-expanded options: days up to "all
  time," limit up to 1000), and any other field this project's current code doesn't yet
  read.

### 1.3 Report the gap
- Before writing any fix, write out plainly: exactly what the live API now provides that
  this project's current code does not use or display, so the fix in STEP 2 is precise
  and complete.

---

## STEP 2 — Update the integration

### 2.1 Fetch logic
- Update the fetch call(s) to this project's own conventions (server-side proxy, direct
  client fetch, scheduled sync job — whatever STEP 1.1 found it already does) so it
  requests the CURRENT full data appropriately — e.g., a sensible default date range and
  a reasonably high product-count limit given the now-much-larger available range, rather
  than whatever narrower defaults it may have been built with originally.

### 2.2 Display logic
- Update the rendered table/card to show the `source` of each product mention (e.g., a
  small tag or icon distinguishing a private-message mention, a group mention, and a
  WhatsApp-story mention) — matching however this project already renders similar
  metadata elsewhere, so it looks native to this project's existing design, not bolted-on.
- If the report includes catalog-match / "outside assistant" status per product, and this
  project's UI has a natural place to reflect that (e.g., alongside how it already shows
  whether a product exists in the internal catalog), wire that in too; if there's no
  natural fit or it's out of scope for this specific page, note this in your final report
  rather than forcing it in.

### 2.3 Tests
Using this project's own existing test/build tooling, add or extend tests confirming:
the fetch requests the full current parameter range correctly; the display correctly
renders the `source` for each product; nothing else on the page or in the project
regresses. If this project has no formal test suite, at minimum perform and document a
manual verification against the live running page.

### 2.4 Commit
Commit + push with a clear message describing the sync.

---

## FINAL REPORT
- Exactly what was found stale in STEP 1.3, and exactly what was changed to fix it.
- Confirm the live /pricing/market-intelligence page now correctly shows source-tagged
  products (including story-detected ones) from the WhatsApp platform's current report.
- Confirm nothing else in this project was broken by this change.
- Any recommended follow-up if something in the WhatsApp platform's API wasn't fully
  usable from this side (e.g., if a field is missing that would be needed for a more
  complete sync later).
- The list of pushed commits, and any redeploy/restart command specific to THIS project
  (investigate and state its own deploy process — do not assume it's identical to the
  WhatsApp platform's docker compose commands, confirm what this project's actual deploy
  step is).

Then STOP and await review.