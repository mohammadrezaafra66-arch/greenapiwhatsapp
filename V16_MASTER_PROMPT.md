# V16 MASTER PROMPT — Afrakala WhatsApp Sender

> **MODE: FULLY AUTONOMOUS.** Execute every PART below, end-to-end, without asking
> the user any questions and without waiting for approval. After each PART: run a
> heavy test suite, and ONLY advance to the next PART once every test passes and the
> feature is verified complete. Commit and push each PART separately. Produce a final
> report at the very end.

---

## 0. CONTEXT (read first, do not skip)

You are working inside the existing project at
`C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`).

Current baseline: **V15**, 237 tests passing, `origin/main` clean.

Stack: **FastAPI + PostgreSQL + Redis + Celery + React/Vite**, Green API gateway,
multi-provider AI key pool. Backend on port **8002**, frontend on port **3002**.
Product/price catalog lives in a **self-hosted Supabase** at `192.168.170.10:8000`.
Connected WhatsApp number: `989122270261`, Green API instance `7105325764`.

### NON-NEGOTIABLE GUARDRAILS (violating any of these is a failure)

1. **NEVER enable Green API polling / `receiveNotification`.** This instance runs in
   **webhook mode only**. Webhook URL and polling are mutually exclusive — enabling
   polling silently kills webhook ingestion. Do not add, re-enable, or "restore" any
   polling loop anywhere.
2. **Do NOT disrupt the running ngrok tunnel or webhook wiring.** Webhook ingestion is
   fragile and has caused outages before. Any ngrok work (PART 5) must be
   non-destructive: back up config first, and if in doubt, only write instructions —
   never tear down the live tunnel.
3. **Do NOT break the send path.** The core campaign send flow
   (`campaign_runner.py` / `group_campaign_runner.py`) must keep working exactly as
   before, except where a PART explicitly changes it. Re-run send-related tests after
   any change that touches these files.
4. **All user-facing UI strings must be in Persian (Farsi), RTL.** Code, variable
   names, and comments stay in English.
5. **Every price shown to a customer must come from live catalog data.** Never fall
   back to "تماس بگیرید" / "call us" when a real price exists. If a price is genuinely
   missing, follow the existing V15 price-enforcement behavior — do not invent one.
6. **Commit and push each PART separately** with a clear message
   (`V16 PART N: <summary>`). Never leave uncommitted work between parts.

### WORKFLOW PER PART

For every PART:
1. Explore the relevant existing code first (don't guess file locations — find them).
2. Implement the change.
3. Write/extend tests. Then run the **full** suite (`pytest`), not just the new tests.
4. Verify the feature actually works (start the backend/frontend or run a targeted
   integration check as appropriate).
5. Only if everything is green: `git add -A && git commit -m "V16 PART N: ..." && git push`.
6. Then move to the next PART.

If a PART cannot be completed because of an external dependency you cannot control
(e.g. the Supabase laptop is powered off, or admin rights are required), do NOT block
the whole run: implement graceful degradation + write a clear instructions file for the
user, commit that, and continue to the next PART. Record it in the final report under
"NEEDS USER ACTION".

---

## PART 1 — Supabase connectivity diagnostic + graceful degradation

**Why:** The products page currently shows "۰ محصول در ۰ برند / محصولی یافت نشد",
which means the app cannot reach Supabase at `192.168.170.10:8000`. Every price/product
feature depends on this. We must (a) diagnose precisely, and (b) make the app degrade
gracefully instead of silently showing an empty list.

### 1.1 Diagnostic script
Create `scripts/check_supabase.py` (or extend an existing health module) that runs, in
order, and prints a clear PASS/FAIL for each:
- TCP reachability of `192.168.170.10:8000` (short timeout, ~3s).
- `GET /auth/v1/health` → gateway liveness.
- An authenticated `GET /rest/v1/<products_table>?select=*&limit=1` using the anon key
  already configured in the project (find where the existing Supabase client reads its
  URL + key; reuse that config, do not hardcode a new key).
- Print the exact HTTP status and a one-line human explanation for each
  (200 = ok, 401/403 = key/permission problem, timeout = laptop off or IP changed).

Run it and capture the result. Write the outcome into the final report.

### 1.2 Graceful degradation in the UI
Wherever the products list is fetched (backend endpoint + the React products page):
- If Supabase is unreachable, return a clear error state to the frontend and show a
  Persian banner on the products page, e.g.
  **«اتصال به Supabase برقرار نیست — لپ‌تاپ Supabase (۱۹۲.۱۶۸.۱۷۰.۱۰) را روشن کنید یا آدرس آن را بررسی کنید.»**
  instead of the misleading "محصولی یافت نشد".
- Distinguish three states in the UI: *loading*, *connected-but-empty*
  ("محصولی یافت نشد"), and *disconnected* (the banner above). They must not look identical.

### 1.3 Tests
Add tests that mock the Supabase client to simulate: reachable+data, reachable+empty,
and unreachable — asserting the endpoint returns the correct state for each. Run the
full suite. Commit + push as `V16 PART 1: Supabase diagnostics + graceful degradation`.

---

## PART 2 — Product monitoring page: browse without searching (item 27)

**Why:** On the products page the user must currently type a search term to find a
product, but they don't have the catalog memorized. They want to *browse* the whole
catalog — grouped by brand — and pick from a list.

### 2.1 Brand-grouped dropdown
On the products page (`/products`), add a **brand-grouped selector**: brands as parent
groups, each product nested under its brand. Selecting a product filters/scrolls the
view to it. Example shape:
```
▼ ال‌جی
   ├ ساید الجی X24 دودی چین
   └ ساید الجی مدل X39
▼ بوش
   └ جاروبرقی بوش 8PRO5
```
Derive brands dynamically from the catalog (do not hardcode the brand list).

### 2.2 Full catalog table
Also add a **complete catalog table** (no search required to populate it) with:
- Brand filter (multi-select or dropdown), a search box (optional, not required to see
  rows), and **pagination** (mirror the existing contacts-table pattern for
  consistency).
- Columns: brand, model/name, price. Sort by price ascending by default (the page
  already sorts cheapest→most-expensive — keep that).

### 2.3 Cross-reference with group mentions (nice-to-have, only if data available)
If the "رصد محصولات در گروه‌ها" data is easily joinable, add columns showing whether a
catalog product has been mentioned in monitored groups, how many times, and the last
mention time. If joining is non-trivial, skip it and note it in the report — do NOT
block PART 2 on this.

### 2.4 Behaviour when Supabase is down
Both the dropdown and the table must show the PART 1 disconnected banner (not an empty
list) when Supabase is unreachable.

### 2.5 Tests
Test the brand-grouping logic and pagination with mock catalog data (including an
empty catalog and a disconnected catalog). Run full suite. Commit + push as
`V16 PART 2: catalog browse (brand dropdown + full table)`.

---

## PART 3 — Advertising links: CRUD + weighted selection + campaign integration (item 29)

**Why:** The user wants to save promotional links (Telegram, WhatsApp, Instagram, a
website) and optionally append them to the end of campaign messages, choosing how many
and whether they're fixed or weighted-random.

### 3.1 Data model
Create a table `advertising_links` with at least:
- `id`
- `url` (string)
- `title` (Persian display label, e.g. «کانال تلگرام»)
- `link_type` (enum/string: `telegram` | `whatsapp` | `instagram` | `website` | `other`)
- `weight` (integer 1–10, default 5)
- `is_active` (bool, default true)
- `created_at`

Add the migration in the project's existing migration style.

### 3.2 Backend CRUD API
Full CRUD endpoints (list / create / update / delete / toggle active) following the
project's existing router conventions. Validate `weight` ∈ [1,10] and `url` is a
plausible URL.

### 3.3 Frontend page «لینک‌های تبلیغاتی»
A new page + nav entry. Table of links with add/edit/delete/enable-disable. Fields:
URL, Persian title, type, weight (1–10 slider or number), active toggle.

### 3.4 Campaign integration
In the campaign builder (both single/parallel and group flows), add:
- A toggle **«افزودن لینک به انتهای پیام»**.
- When ON: a number input **«تعداد لینک»** (how many links to append, capped at the
  number of active links).
- A mode selector: **«ثابت»** (always the same top-weighted / user-picked links) vs
  **«رندوم وزنی»** (weighted-random by the 1–10 weight).

### 3.5 Runner: append links to the message
In `campaign_runner.py` and `group_campaign_runner.py`, AFTER the message body (and
after any product block) is composed, append the selected links, each on its own line
with its Persian title, e.g.:
```
... متن پیام ...

🔗 کانال تلگرام: https://t.me/afrakala
🔗 اینستاگرام: https://instagram.com/afrakala
```
Implement **weighted-random selection**: probability proportional to `weight`, no
duplicates within a single message, only `is_active` links eligible. If "تعداد لینک"
exceeds the number of active links, use all active links.

**Guardrail:** this must be purely additive to the message. Do not alter the existing
message-composition logic above it. Re-run all send-path tests.

### 3.6 Tests
Unit-test the weighted-random selector (distribution roughly tracks weights over many
runs; no duplicates; respects the count cap; ignores inactive links). Test CRUD
endpoints. Test that a campaign with the toggle OFF produces byte-identical output to
before (regression guard). Run full suite. Commit + push as
`V16 PART 3: advertising links (CRUD + weighted append in campaigns)`.

---

## PART 4 — Verify live per-message pricing (item 30)

**Why:** The user needs prices to reflect the catalog *at the moment each message is
sent*, not a snapshot cached when the campaign started. If a price changes mid-campaign,
later messages must use the new price.

### 4.1 Investigate (report first, then fix only if needed)
Read the send flow in `campaign_runner.py` and `group_campaign_runner.py`. Locate every
place the product/price data is fetched (the Supabase query or `get_products()`-style
call). Determine precisely:
- Is the fetch **inside** the per-contact / per-group send loop (→ real-time, correct)?
- Or **before/outside** the loop, then reused for every message (→ stale, a bug)?

Write the exact file + line + verdict into the final report.

### 4.2 Fix if it's cached
If prices are cached at campaign start, refactor so each message fetches (or refreshes)
the price at send time. To avoid hammering Supabase, a **short TTL cache (≤60s)** is
acceptable — that still reflects a mid-campaign price change within a minute, which
meets the requirement. If it's already per-message/real-time, change nothing and just
confirm it in the report.

### 4.3 Tests
Add a test that simulates a price change between two messages in the same campaign run
and asserts the second message reflects the new price (or, if a TTL cache is used, after
the TTL). Run full suite. Commit + push as
`V16 PART 4: verify/ensure live per-message pricing`.

---

## PART 5 — Smart warm-up enhancements (item 31)

**Why:** V15 PART 8 added a basic auto warm-up toggle (10-day schedule: days 1–3 receive
only, 4–7 up to 3 replies/day, 8–10 up to 10 replies/day, then "ready"). The user wants
it smarter and more human-like, plus visibility.

Build on the existing warm-up system — do NOT rewrite it from scratch.

### 5.1 Outbound simple-message pool
Add a configurable pool of ~10–15 short, natural Persian phrases the warm-up can send to
**prior contacts** (people who already messaged this number), e.g. «سلام، خوب هستید؟»,
«ممنون از خریدتان. کمکی از دست ما برمی‌آید؟». Store the pool so it's editable (a simple
table or config the user can extend later). Warm-up picks randomly from active phrases.

### 5.2 Human-like timing
Spread warm-up actions across the day instead of firing them all at once (e.g. a couple
in the morning, one in the afternoon), with small randomized jitter between sends. Keep
within the existing per-day caps for the current warm-up stage — never exceed them.

### 5.3 Warm-up dashboard
A page showing every account currently in warm-up with: its stage/day, a progress bar to
"ready", replies sent today vs. the day's cap, and a "ready ✅" badge when complete.

### 5.4 Batch controls
A **«شروع گرم‌سازی همه»** action to toggle warm-up ON for many newly-added accounts at
once, and a matching "stop all".

### 5.5 Guardrails
Warm-up must remain OFF by default on every account (as in V15). It must never message a
number that hasn't previously contacted this account. It must never use polling. Respect
the stage caps strictly.

### 5.6 Tests
Test stage transitions, the daily-cap enforcement (never exceeds the cap even with
batch + timing jitter), the phrase-pool random selection, and that warm-up defaults OFF.
Run full suite. Commit + push as `V16 PART 5: smart warm-up (phrases, timing, dashboard, batch)`.

---

## PART 6 — ngrok as a Windows service (item 28)

**Why:** ngrok has no process supervision, so when it dies, webhook ingestion silently
stops (this caused a 2-day outage). Installing it as a Windows service makes it
auto-start on boot and restart on failure.

**IMPORTANT — this touches the live tunnel, so be conservative:**

### 6.1 Facts to honor
- The reserved domain `multidisciplinary-jeri-physiognomically.ngrok-free.dev` is the
  account's **free static domain** — it is persistent and valid; the service will bind
  to it via config.
- Use **`ngrok.exe` / `ngrok.cmd`**, NOT the npm shim.
- The config file must be **version 3** (`version: "3"`) and contain the authtoken and a
  tunnel definition pinned to that domain and the correct local port (the port the
  webhook currently forwards to — discover it, don't assume).
- `ngrok service install` requires **Administrator** privileges.

### 6.2 Non-destructive procedure
1. Locate the current ngrok config (`ngrok.yml`) and the exact tunnel command used by
   the current `شروع.bat`. **Back up** the config file first.
2. Produce a correct **version-3** `ngrok.yml` (authtoken + the static domain + the right
   local port) — write it to the project, do not overwrite the backup.
3. Generate a file **`NGROK_SERVICE_SETUP.md`** at the project root containing the exact,
   copy-pasteable **Administrator PowerShell** commands, in order:
   - Verify `ngrok.exe` path and version.
   - `ngrok service install --config <path-to-v3-ngrok.yml>`
   - `ngrok service start`
   - Verification: check the service is running and the tunnel is up at the static domain.
   - A **fallback** section using **NSSM** (and, as a second fallback, Windows Task
     Scheduler "at startup") in case `service install` fails with exit code 5 / a
     permissions error.
   - A rollback note (how to `ngrok service stop` / uninstall and return to `شروع.bat`).
4. **Only attempt to run the install automatically if it will NOT disrupt the currently
   running tunnel and you have the required privileges.** If there is any risk to the
   live webhook, do NOT run it — leave the tunnel exactly as-is and rely on the
   `NGROK_SERVICE_SETUP.md` instructions for the user to run manually. Per the user's
   instruction: if it can't be done cleanly/automatically, hand them the commands.

### 6.3 Output
Commit + push `NGROK_SERVICE_SETUP.md` + the v3 config as
`V16 PART 6: ngrok Windows-service setup (config + admin instructions)`. Record in the
final report whether the service was installed automatically or is awaiting the user's
admin run.

---

## FINAL REPORT (produce after all parts)

Output a single summary containing:
- Test count before (237) → after, and per-PART deltas, with "zero regressions" confirmed.
- One line per PART: done / done-with-caveat, and what was built.
- A **"NEEDS USER ACTION"** section listing anything the user must do themselves
  (e.g. power on the Supabase laptop if PART 1 found it unreachable; run the admin
  commands in `NGROK_SERVICE_SETUP.md` if PART 6 could not self-install).
- Confirmation that: polling was never enabled, the webhook/ngrok tunnel was not
  disrupted, and the send path is unchanged except where PART 3/4 intentionally touched it.
- The list of pushed commits.

Then stop and await the user's review. Do not start any further work.