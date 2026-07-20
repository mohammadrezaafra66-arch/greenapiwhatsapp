# V35 MASTER PROMPT — Afrakala WhatsApp Sender
## Stop auto-status, contact categories, guided onboarding wizard, dashboard chart fix

> **MODE: FULLY AUTONOMOUS, RESUMABLE ACROSS SESSION LIMITS.** Execute every PART
> end-to-end WITHOUT asking questions and WITHOUT waiting for approval. After each PART:
> run a heavy test suite and verify it works; only advance once every test passes. Commit
> and push each PART separately — this is critical for resumability.
>
> **If you hit a usage/session limit mid-part:** stop cleanly wherever you are (do not
> leave the working tree in a broken uncommitted state if avoidable). **On the very next
> invocation of this same prompt** (whether restarted by the user or continued in a new
> session): FIRST run `git log --oneline -15` and `git status` to determine exactly which
> PARTs are already committed/pushed, then resume from the next incomplete PART — do NOT
> restart from PART 1 or redo already-completed work. Use a visible task list (todos) for
> the 5 parts below so progress is easy to check at a glance, matching how V33 was tracked.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main — V17 through
V34 are merged and deployed (mesh warm-up, V26 group-monitoring, V27 anti-ban hardening,
Telegram platform, V28-V34 «همکاری تیمی» / Team Collaboration). ~950 tests passing.

**Research finding to build to (already confirmed, do not re-research):** Green API
supports POSTING your own WhatsApp Status (`SendTextStatus` and similar) and getting
view/delivery stats (`GetStatusStatistic`), but there is NO documented method to reply to
or react to someone ELSE's status. Do not attempt to build any "reply to/react to others'
status" feature — it isn't supported by Green API, and status-bot-style automation was
already explicitly excluded from this project (V26 decision) due to high ban risk.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only stays intact.
2. **Do NOT touch ngrok/webhook wiring, the mesh (V17–V25), V26 group-monitoring, V27
   anti-ban hardening, or the Telegram platform**, except PART 1's investigation (read-only
   until a fix location is confirmed).
3. **Do NOT build any feature that replies to or reacts to other users' WhatsApp Status
   updates** — not supported by Green API and out of scope per the V26 decision.
4. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English. Shamsi dates
   wherever a date is shown to the user (reuse the existing Shamsi utility from V29's log
   page if present).
5. **Commit + push each PART separately** (`V35 PART N: ...`).

### WORKFLOW PER PART
Explore existing code first → implement → write/extend tests → run the FULL existing test
suite → verify zero regressions → commit + push → next PART.

---

## PART 1 — Investigate and stop the automatic daily WhatsApp Status post

**Context:** A text status is being auto-posted every day at ~10:00 (Tehran time) from
number 989122270261. The user is not sure whether this was configured inside this
codebase or set up separately (e.g., an external script, Windows Task Scheduler, or
directly via the Green API console/API outside this app). **Investigate before assuming
either way** — this determines whether the fix is a code change here or guidance for the
user to act on elsewhere.

### 1.1 Investigate (in this order)
- Search the ENTIRE claudegreenapi codebase (not just recently-touched files) for any
  scheduled task, Celery beat entry, cron-like job, or code path that calls
  `sendTextStatus` / `SendTextStatus` / any "status"-related Green API method, for
  instance `7105325764` (989122270261) or any instance. Check `celery_app.py`'s
  `beat_schedule`, any `advertising_links`/`content`-related scheduling code, and any
  legacy pre-V17 features that might not be covered by this conversation's later history.
- If nothing is found in this codebase, check the HOST machine (Windows) for anything that
  could be calling Green API's status endpoint on a schedule: Windows Task Scheduler
  entries (`schtasks /query`), any other running script/cron on this machine, or another
  local project directory that might contain such a scheduler (the user has at least one
  other unrelated project on this machine — `multi-messaging-platform` — found during a
  prior diagnostic; quickly check if IT has any status-posting code targeting this number,
  but do not modify that separate project without flagging it clearly first).

### 1.2 Fix or report
- **If found inside claudegreenapi:** disable/remove the scheduled status-posting code
  (comment out or delete the beat entry / scheduled task), guarded so it can't silently
  re-enable itself. Add a test asserting no status-send task is registered/scheduled.
- **If found elsewhere (external to this codebase):** do NOT attempt to modify a different
  project or the OS scheduler without being certain — instead, clearly document EXACTLY
  where it lives (file path, task name, or "external — not in this codebase") in the final
  report, with precise instructions for how the user can disable it themselves (e.g., the
  exact `schtasks` command, or which file/script to edit in the other project).
- **If genuinely not found anywhere accessible:** report this clearly and suggest the most
  likely explanation (e.g., a one-time-but-recurring queued status via Green API's own
  status queue) so the user can investigate via the Green API console (e.g., checking
  `GetStatusStatistic`/any queued sends) if my search comes up empty.

### 1.3 Tests
If a fix was applied in this codebase: a test confirms no status-posting task is
scheduled/registered anywhere in `celery_app.py`'s beat schedule. If external: no test
needed here, just a clear report entry.
Run full suite. Commit + push `V35 PART 1: investigate and stop automatic daily status post`.

---

## PART 2 — Confirm sender/contact assignment is usable (no new build expected)

**Context:** The user asked (31.1/31.2) whether the system currently lets them (a) mark
which accounts are usable as "warm" senders, and (b) specify which warm sender sends
requests to which contacts (friends/colleagues/employees). This was already built in
V28 PART 2 (sender selection) and V30 PART 1 (full dedicated UI). This PART is a
verification pass, not a rebuild.

### 2.1 Verify
- Confirm, by reading the actual current `/team-collaboration` page code, that: (a) the
  user can designate/see which accounts are eligible warm senders (with the warmth score
  from V30 PART 8), and (b) the user can pick a sender and manage/assign THAT sender's own
  contact list, each contact tied to specific cold account(s). If any part of this is
  broken or not actually reachable in the UI (contradicting what the V30 report claimed),
  fix it; if it's genuinely fine, make no code change — just confirm in the report with
  specific evidence (e.g., the exact page/component and API calls involved).

### 2.2 Tests
No new tests needed if nothing was broken; if a gap is found and fixed, add a test for it.
Run full suite. Commit + push `V35 PART 2: verify sender/contact assignment UI (fix if broken)`
— or skip the commit and just note "no fix needed" in the report if everything checks out.

---

## PART 3 — Contact relationship category + optional referral note

### 3.1 Schema
- Add a `relationship` field to `warmup_helper` (contact): an enum/choice of
  «دوست» (friend) / «همکار» (colleague) / «کارمند» (employee) / «فامیل» (family) — shown
  as a dropdown when adding/editing a contact.
- Add an optional free-text field, e.g. `referral_note` (nullable): a short note such as
  «شماره شما را آقای X داده» that, when present, is naturally incorporated into that
  contact's AI-generated ask-messages (via the existing V31/V33 unified message generator)
  — pass it as additional context to the AI prompt alongside the job_title/years_experience/
  personal_benefit_note fields already used, so the generated text can reference it
  naturally when appropriate. This field is independent of `relationship` — any category
  may optionally have a referral note.

### 3.2 UI
- Add the relationship dropdown and the optional referral-note text field to the existing
  contact add/edit form on `/team-collaboration`.

### 3.3 Tests
Saving a contact with a relationship category persists correctly; the referral note, when
present, is passed into and reflected in generated ask-message content (mock the AI call
and assert the note text/context reaches the prompt); omitting the note works as before
(no regression to existing message generation).
Run full suite. Commit + push `V35 PART 3: contact relationship category + referral note`.

---

## PART 4 — New guided onboarding wizard page: «راه‌اندازی» (Setup)

**Why:** A dedicated, time-gated, step-by-step wizard that walks the user through
correctly onboarding a brand-new phone number from SIM insertion all the way to Team
Collaboration enrollment — encoding every anti-ban rule established throughout this
project (SIM aging via real phone use, the wait before registering WhatsApp, the 24h wait
before connecting to Green API) as an enforced, guided sequence rather than something the
user has to remember.

### 4.1 Data model
- `account_onboarding`: `id`, `phone_number`, `phone_make_model` (free text, e.g. "Samsung
  A14"), `sim_inserted_at` (timestamp, user-entered), `whatsapp_activated_at` (timestamp,
  set when the user confirms step 2 is done), `green_api_login_prompted_at`,
  `green_api_connected_at` (set once the user confirms/or the corresponding instance
  becomes authorized), `current_step` (integer/enum), `created_at`.
- Fixed gates (ship these as constants): **Gate A — SIM insertion → WhatsApp activation:
  24 hours** (per the user's decision — matches the project's standard wait). **Gate B —
  WhatsApp activation → Green API login: 24 hours** (the project's existing, proven rule).

### 4.2 The guided flow (Persian, RTL, Shamsi date+time ALWAYS visible on this page)
- **Step 1 — record SIM insertion:** a form where the user enters: the phone number, the
  exact date+time (Shamsi, but store as a real timestamp) they put the SIM in a phone, and
  the phone's make/model. Save `sim_inserted_at`. Show the Persian guidance for this
  waiting period explicitly on the page, e.g.: «در این مدت با این سیم‌کارت تماس بگیرید و
  پیامک رد و بدل کنید — با شماره‌های واقعی، نه به‌صورت خودکار» (call/text normally with
  real numbers during this window — reuse wording consistent with the project's
  established anti-ban guidance, e.g. the V22 QR-screen rules).
- **Locked/waiting state:** until Gate A's 24h elapses, the page shows a clear countdown/
  status: «هنوز زود است — تا ساعت [محاسبه‌شده] صبر کنید» with the exact unlock time shown
  in Shamsi date+time.
- **Step 2 — unlocked automatically when Gate A elapses:** the page now shows: «حالا
  می‌توانید اکانت واتساپ این شماره را روی همین گوشی بالا بیاورید و تنظیمات (نام، عکس
  پروفایل و…) را کامل کنید.» A button/confirmation for the user to mark this done, which
  sets `whatsapp_activated_at` = now.
- **Step 3 — waiting again (Gate B):** once step 2 is confirmed, show the 24h countdown
  again with the exact unlock time (Shamsi), and the reminder: «در این ۲۴ ساعت، این شماره
  را طبیعی روی گوشی استفاده کنید — هنوز به Green API وصل نکنید.»
- **Step 4 — unlocked automatically when Gate B elapses:** the page shows: «حالا وارد
  Green API شوید، این شماره را با اسکن QR وصل کنید، سپس دکمهٔ «همکاری تیمی» را برای این
  اکانت فعال کنید.» Link/redirect into the existing account-creation/QR flow and the
  existing Team Collaboration enrollment UI — reuse them, do not duplicate.
- At every step, show a short, clear, single next-action instruction — never more than one
  action expected at a time.

### 4.3 List/dashboard view
- A list of all onboarding-in-progress numbers with their current step and next-unlock
  time (Shamsi), so the user can track multiple numbers being onboarded at once.

### 4.4 Tests
Step 1 form saves correctly; the page correctly shows "locked" until Gate A's 24h elapses
(mock time) and unlocks exactly at the boundary; step 2 confirmation sets the timestamp and
starts Gate B's countdown; step 4 unlocks at Gate B's boundary and links correctly into the
existing QR/Team-Collaboration flows; Shamsi date/time renders correctly throughout; the
list view shows multiple in-progress onboardings with correct next-unlock times.
Run full suite. Commit + push `V35 PART 4: guided onboarding wizard (راه‌اندازی) page`.

---

## PART 5 — Fix the per-account "sent today" dashboard chart

**Context (already diagnosed, confirmed root causes — fix both):**
1. The `/dashboard/stats` endpoint's `detail` list includes soft-deleted accounts, so a
   duplicate/stale account row (same display name, `status=deleted`) appears alongside the
   real one on the "ارسال امروز به تفکیک حساب" chart's x-axis.
2. The per-account chart uses only `accounts.sent_today` (the legacy campaign-only
   counter), so any account whose today's activity came from Team Collaboration, mesh, or
   status sends shows 0 even when it genuinely sent messages today — because V30 PART 8's
   cross-ledger `real_sent_today` fix was only applied to the TOTAL, not the per-account
   breakdown.

### 5.1 Fix
- Exclude soft-deleted (and consider excluding fully disconnected/removed) accounts from
  `/dashboard/stats`'s `detail` list used to build this chart.
- Extend the per-account breakdown to use the SAME cross-ledger logic as the total
  (`send_metrics.real_sent_today`, already built in V30 PART 8) computed PER ACCOUNT
  instead of only the global sum — so the bar chart correctly reflects campaign + mesh +
  Team Collaboration + status sends for each account, using the correct Tehran-calendar
  "today" boundary already established.

### 5.2 Tests
A soft-deleted account no longer appears in the chart data; an account whose only activity
today was Team Collaboration sends now shows the correct non-zero count in the per-account
breakdown; the existing top-line total test from V30 PART 8 still passes unchanged.
Run full suite. Commit + push `V35 PART 5: fix per-account dashboard chart (exclude deleted, cross-ledger counts)`.

---

## FINAL REPORT
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- PART 1: exactly where the automatic status-posting was found (in-app or external), what
  was done, and — if external — the precise steps the user must take themselves.
- PART 2: confirmation (with evidence) that sender/contact assignment already works, or
  what was fixed if it didn't.
- PART 3: relationship categories + referral note working, with a sample generated message
  showing the referral note naturally incorporated.
- PART 4: the new «راه‌اندازی» page fully described — the two 24h gates, the step flow,
  Shamsi date/time display, and how it hands off into the existing QR/Team-Collaboration UI.
- PART 5: confirm the chart no longer shows duplicates and now reflects real per-account
  activity across all ledgers.
- Confirm: polling never enabled; ngrok/webhook untouched; mesh/V26/V27/Telegram code
  unchanged (except PART 1's investigation); no feature was built for replying to/reacting
  to others' WhatsApp Status (confirmed unsupported/out of scope).
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
The onboarding wizard (PART 4) encodes real anti-ban discipline into the product itself —
this is a durable improvement regardless of any single number's outcome. It still can't
guarantee any given SIM survives; it just ensures the established best practices are
followed consistently instead of relying on memory.