# V48 MASTER PROMPT — Afrakala WhatsApp Sender
## Unified "all accounts at a glance" status page

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
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, through V47.

A recent audit confirmed: every warmth-score/eligibility calculation in this project
already routes through ONE shared, live evaluator — the numbers are accurate and
internally consistent everywhere they appear today. The gap is purely presentational:
this correct information is currently scattered across four separate pages —
`/accounts` (connection state), `/warmup` (warmth score, peer_age_days,
_recent_incident_count), `/protection` (incident history, account_health/
account_incidents), and `/team-collaboration` (role — mesh enrollment state,
is_warm_peer, warmup_team_enrollment/TC contacts, eligibility via
check_sender_eligibility + any warmup_sender_config override) — plus recent send/receive
activity that lives with the accounts data.

THIS PROMPT builds ONE new page that pulls all of this together into a single row-per-
account view, so the user never has to cross-reference four different pages to answer
"what is this account's full current situation?"

### NON-NEGOTIABLE GUARDRAILS
1. This is a PURE AGGREGATION page. Do NOT reimplement any scoring/eligibility/incident
   calculation — call the EXACT existing functions/services already confirmed correct
   (the shared warmth evaluator, check_sender_eligibility, the mesh dashboard's own
   per-account data assembly, etc.). If two existing sources describe the same fact
   slightly differently (e.g., a label vs. a raw value), prefer showing the exact value
   the source-of-truth page already shows, not a new derived one.
2. Do NOT remove or change any of the four existing pages — this is an ADDITIONAL page,
   a convenience overview, not a replacement.
3. NEVER enable Green API polling. Webhook-only stays intact.
4. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
5. Commit + push each PART separately ("V48 PART N: ...").

### WORKFLOW PER PART
Read the actual current data-fetching code behind each of the four existing pages first
(don't assume) → build the aggregation reusing those exact functions → write/extend
tests → run the FULL existing test suite → verify zero regressions → commit + push →
next PART.

---

## PART 1 — Investigate the four existing data sources precisely

### 1.1 Investigate
- For each of `/accounts`, `/warmup`, `/protection`, `/team-collaboration`: identify the
  EXACT backend function(s)/endpoint(s) each page calls to get its per-account data, and
  the exact shape of what each returns.
- Confirm the single shared warmth/eligibility evaluator's exact function signature and
  how each existing page currently calls it, so the new page reuses it identically.

### 1.2 Tests
No code change yet — a short findings note (as a code comment or a small doc file) is
sufficient here; commit + push "V48 PART 1: inventory the four existing account-data sources".

---

## PART 2 — Build the aggregation endpoint

### 2.1 Backend
- Add one new endpoint (e.g. `GET /api/v1/accounts/overview` or similar, naming
  consistent with existing route conventions) that, for EVERY account in the system,
  assembles one row combining:
  - Connection state (from the accounts source).
  - Warmth score + level, days-connected, incident-free streak (from the shared
    evaluator — call it directly, do not recompute).
  - Incident history summary (most recent incident type + date, total incident count)
    from the protection/health source.
  - Current role: mesh peer (yes/no + which state), Team Collaboration sender (yes/no +
    contact count if sender), cold/recipient account (yes/no), or none of these.
  - Sender-eligibility status + whether an override is currently in effect (from
    check_sender_eligibility + warmup_sender_config).
  - Recent activity: sent/received today (and ideally a short recent trend, reusing
    whatever the accounts/dashboard page already computes for this).
- This endpoint should call the EXISTING underlying functions for each of these pieces
  (per PART 1's findings) rather than querying raw tables itself where a suitable
  existing service function already exists.

### 2.2 Tests
For a set of accounts covering every role/state combination (healthy sender, too-young
peer, yellowCarded, cold/recipient-only, unassigned/no-role), the aggregation endpoint
returns a row per account with all fields populated correctly, matching exactly what
each individual existing page would show for that same account (cross-check against the
existing per-page functions directly in the test, not against hardcoded expected
values, so this test would catch a future drift automatically).
Run full suite. Commit + push "V48 PART 2: build the all-accounts aggregation endpoint".

---

## PART 3 — Build the frontend overview page

### 3.1 Frontend
- Add a new page (e.g. `/accounts-overview` or a name consistent with the just-
  reorganized navigation from V47 — place it sensibly within the existing nav groups,
  likely under Protection & health or Numbers, whichever fits best given the V47
  reorganization) showing one row per account with all the PART 2 fields, in a clear,
  sortable/filterable table (e.g. sortable by warmth score, filterable by role or
  eligibility status).
- Each row should link out to the relevant detail page (e.g. clicking an account's
  "role: TC sender" links to its detail on `/team-collaboration`) rather than
  duplicating deep functionality here — this page is a map/overview, not a replacement
  for the detail pages.
- Add this new page to the sidebar navigation (matching V47's structure/conventions) and
  to the ⌘K command palette search, consistent with how other pages are registered.

### 3.2 Tests
The page renders correctly with real/mocked data across every role/state combination;
sorting and filtering work correctly; each row's links correctly point to the right
existing detail page; the new nav entry appears correctly without breaking V47's
nothing-lost route inventory (re-run that automated diff check to confirm THIS
addition doesn't itself break anything, and that it's correctly counted as an
intentional addition, not a false regression).
Run full suite (backend + frontend build/pure-module tests). Commit + push
"V48 PART 3: build the unified all-accounts overview page".

---

## PART 4 — Final wiring + full regression pass

### 4.1 Tests
Full end-to-end simulation: for a realistic mixed set of accounts (matching the real
current live accounts' actual roles/states as closely as feasible), confirm the overview
page's every field matches what the four existing individual pages would show for the
same accounts. Re-run the FULL pre-existing suite to confirm zero regressions.
Run full suite. Commit + push "V48 PART 4: final wiring + full regression pass".

---

## PART 5 — Redeploy (do this yourself)

Run:
```
docker compose build frontend
docker compose up -d frontend
docker compose up -d --force-recreate worker-general worker-webhooks beat backend
```
Verify live: all containers healthy; the new overview page loads and its data matches
a live spot-check against at least one of the four existing pages for the same account.

---

## FINAL REPORT
- Confirm every field on the new overview page is sourced from the existing, already-
  confirmed-correct evaluator/services — no new calculation logic was introduced.
- A live example: pick 2-3 real current accounts and show their overview-page row next
  to what each of the four existing pages independently shows for the same account,
  confirming they match.
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- Confirm the V47 route-inventory diff still passes with only the new page counted as
  an intentional addition.
- The list of pushed commits, and confirmation the redeploy was executed and verified.

Then STOP and await review.