# V29 MASTER PROMPT (REVISED — extends V28, no duplicate schema) — Afrakala WhatsApp Sender
## «همکاری تیمی» (Team Collaboration): full personnel-outreach warm-up system

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking questions and
> WITHOUT waiting for approval. After each PART: run a heavy test suite and verify it
> works; only advance once every test passes. Commit and push each PART separately.
> Produce a final report.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main — V28
(`95230f5`, `83008c3`, `179595d`, `dcc0d67`) is ALREADY MERGED: `warmup_helper` (contact),
`warmup_helper_task` ((contact × cold) link), `warmup_helper_config`
(`soft_warning_threshold`), `outreach_brief` (append-only per-sender brief), the shared
`peer_pacer` + V27 `can_send_now` rails in `warmup_helper_engine`, all already exist and
are tested/deployed.

**⚠️ THIS PROMPT EXTENDS V28 — it does NOT create a parallel "team_collab_*" schema.**
Use exactly this reconciliation (confirmed against the live V28 code):
- **Contacts:** reuse `warmup_helper` — ADD new NULLABLE columns for the rich profile
  (`job_title`, `years_experience`, `personal_benefit_note`, `phone_secondary`). Do NOT
  create a separate contacts table.
- **Contact↔cold-account link:** reuse `warmup_helper_task` (already the (helper × cold)
  pairing). Add a DB-level `UNIQUE(helper_id, cold_instance_id)` constraint (currently only
  app-enforced — make it a real constraint now).
- **Conversation threads:** ADD a NEW table for this (nothing like it exists yet), keyed by
  `(helper_id, cold_instance_id)` — see PART 3.
- **Sender brief:** `outreach_brief` is append-only (a history log) — ADD a `is_current`
  boolean flag (or equivalent "latest per sender" mechanism) so the system always knows the
  ACTIVE brief per sender without relying on `created_at` ordering.
- **Per-sender enable/toggle:** today the toggle is GLOBAL — ADD a per-sender enabled flag
  (V29 is the first place this is needed).
- **`sender_instance_id` nullability:** it's nullable on legacy V25 rows (meaning "main
  account"). Continue to resolve null via the existing `resolve_main_sender_instance_id`
  helper — do not change existing rows or break that resolution.
- **Pacing/health:** ALL new sends in this prompt (ask-messages, reminders, thank-yous, AND
  the new cold-account auto-reply) MUST route through the EXISTING `warmup_helper_engine`
  rails (V27 `can_send_now` + the shared `peer_pacer`, Tehran→UTC aware) — do not add a
  second/parallel send path.

**System name:** call this feature **«همکاری تیمی»** (Team Collaboration) in the Persian
UI wherever it's user-facing, even though the underlying tables remain `warmup_helper*`.

**What this builds, in the user's own words, organized (unchanged from the original ask):**
1. Each SENDER account messages only ITS OWN dedicated set of contacts.
2. Each sender has a content BRIEF (a short description) defining what its messages are
   about; AI generates the actual text from that brief.
3. All existing anti-ban/anti-block rules apply (reuse V27's gates and pacing — do not
   invent new, weaker rules).
4. Total contacts needed: ~25–30 people, saved with FULL NAME (first + last — mandatory).
5. When saving a contact, ALSO record: their job/position at Afrakala, years of
   specialized experience, and a note on what benefit this system has for THEM personally
   — the AI uses this so the ask-message can explain to them exactly why helping is
   relevant/useful to them.
6. A dedicated area to manage the roster of COLD account phone numbers that need warming,
   and to configure exactly which sender → which contacts → which cold accounts.
7. Each ask-message references AT MOST 2 cold accounts. Preferably each contact has ONE
   fixed "path" (a consistent cold account they talk to, optionally via both a personal
   and a work number), and follow-up asks continue the SAME topic/thread (e.g. "did you
   send my TV?" → later steps continue that same conversation) rather than a fresh random
   topic each time.
8. When a contact actually sends the requested message (detected via webhook across the
   inbox the system already has access to), automatically send a thank-you FROM that
   contact's assigned sender account.
9. When the contact sends the requested message to a cold account, the COLD ACCOUNT must
   automatically send an appropriate, properly-timed AI reply back to the contact —
   continuing that thread's topic — per Green API's + our own anti-ban timing standards.
10. If a contact hasn't sent the requested message within ~45–60 minutes, send ONE
    automatic reminder from their assigned sender account.
11. Each cold account gets its own toggle to join «همکاری تیمی»; once enabled, everything
    runs automatically over a 10-day window per the standards below.
12. A dedicated log/table (separate from the existing inbox/outbox) showing exactly which
    account sent what to which account and what was received, with Shamsi dates + exact
    times — its own page, parallel to (not mixed with) the regular inbox/send-queue.
13. (Handled — see "included suggestions" below.)
14. The system must itself ANALYZE how warm a candidate sender account actually is and
    show this status on the dashboard (not just accept a manual flag).
15. Use wa.me click-to-chat links for cold accounts in messages — never raw phone numbers.

**Design decisions made from the spec (stated, not asked):**
- A contact's "path" is preferably ONE fixed assigned cold account (optionally with a
  second "شماره کاری"/work number for the same contact talking to the same cold account),
  but up to 2 assigned cold accounts may be referenced together in a single message, as an
  explicit ceiling, not a default target.
- «همکاری تیمی» only starts sending for a given cold account AFTER that account's existing
  24h post-authorization cooldown has cleared — reuse the SAME cooldown timing the mesh
  already uses.
- The cold account's auto-reply is ONE contextual reply per SCHEDULED ask-step (not a
  live, open-ended, general-purpose chatbot) — the conversation progresses through
  system-scheduled steps over the 10 days, each followed by exactly one cold-account reply.

**Included suggestions (built in by default — flag/remove in the report if unwanted):**
- **Real product/price grounding:** reuse the existing live Supabase product-pricing feed
  so thread topics like "did you send my TV?" can reference REAL current products/prices.
- **Sender warmth score (not just pass/fail):** extend V27 PART 3's binary 14-day/clean-
  history gate into a computed score/level (کم/متوسط/بالا) shown on the dashboard.
- **Thread-level safety flagging:** if a forbidden/sensitive word appears in either
  direction of a thread, pause THAT thread and alert the admin — don't halt the system.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only stays intact.
2. **Do NOT touch ngrok/webhook wiring, the mesh (V17–V25), V26 group-monitoring, V27
   anti-ban hardening, or the Telegram platform.** This is additive.
3. **Every send in this prompt routes through the EXISTING `warmup_helper_engine` rails**
   (V27 `can_send_now` + shared `peer_pacer`) — sender-side AND cold-account-side alike.
4. **Full name (first + last) is mandatory** on `warmup_helper` going forward — reject
   saves without it; existing rows are not retroactively broken, but new saves require it.
5. **Never leak account numbers/instance ids/system labels into any generated text** —
   reuse the exact V24 hard filter, for BOTH ask-messages and cold-account auto-replies.
6. **Cold accounts must not send if within their own 24h cooldown or otherwise
   unhealthy** — `can_send_now` gates the cold account's auto-reply too, not just the
   sender's outbound ask.
7. **All UI strings Persian (Farsi), RTL** — labeled «همکاری تیمی». Code/vars/comments
   English. Use Shamsi dates in the dedicated log (reuse an existing Shamsi utility if one
   exists in the codebase; add one if not).
8. **Commit + push each PART separately** (`V29 PART N: ...`).

### WORKFLOW PER PART
Explore the ACTUAL current `warmup_helper`/`warmup_helper_task`/`outreach_brief`/
`warmup_helper_engine` code first (don't assume — verify against what V28 really built) →
extend it → write/extend tests → run the FULL existing test suite → verify zero
regressions (especially V25/V27/V28's existing tested behavior) → commit + push → next PART.

---

## PART 1 — Extend `warmup_helper` with the rich profile + name-mandatory

### 1.1 Schema (ALTER, don't create a parallel table)
- Add nullable columns to `warmup_helper`: `job_title`, `years_experience` (integer),
  `personal_benefit_note` (text), `phone_secondary` (nullable — «شماره کاری»).
- Make `name` on `warmup_helper` NOT NULL going forward for new inserts (add an
  application-layer + DB-level constraint/validation; if existing rows have null/empty
  names, leave them but flag them in the final report rather than guessing a fix).
- Add DB-level `UNIQUE(helper_id, cold_instance_id)` on `warmup_helper_task` (currently
  only app-enforced).
- Add `is_current` (boolean) to `outreach_brief` so exactly one row per
  `sender_instance_id` can be flagged current/active (enforce uniqueness of "current" per
  sender at the app layer at minimum).
- Add a per-sender `is_enabled` flag (the toggle is currently global — this prompt needs a
  per-sender one; keep the existing global toggle working for whatever it currently gates,
  and add the new per-sender flag alongside it without breaking existing behavior).

### 1.2 Tests
Saving a helper with no name is now rejected; new nullable columns save/read correctly;
the new UNIQUE constraint prevents a duplicate (helper, cold_instance) pair; `outreach_brief`
correctly tracks exactly one current brief per sender; the new per-sender toggle doesn't
break the existing global one; ALL existing V25/V28 tests still pass unchanged.
Run full suite. Commit + push `V29 PART 1: extend warmup_helper with rich profile + name-mandatory + per-sender toggle`.

---

## PART 2 — Roster + mapping UI (extends V28's existing sender/contact-list UI)

### 2.1 UI
- Extend V28's existing per-sender contact-list UI (do not rebuild it) to also capture/
  edit: job_title, years_experience, personal_benefit_note, phone_secondary.
- Extend the existing cold-account picker/roster area so a contact can be linked to 1
  (preferred) or up to 2 `warmup_helper_task` cold-account assignments, with a clear
  Persian hint: «برای سادگی و طبیعی‌تربودن، ترجیحاً هر مخاطب را فقط به یک اکانت سرد اختصاص
  دهید.»
- Surface the per-sender «همکاری تیمی» enable toggle from PART 1.

### 2.2 Tests
Rich-profile fields save/edit correctly via the extended API; assigning a 3rd cold account
to one contact is rejected with a clear Persian message (ceiling of 2); per-sender toggle
persists. Run full suite. Commit + push `V29 PART 2: extend roster + mapping UI with rich profile + per-sender toggle`.

---

## PART 3 — Conversation threads + thread-aware, personalized AI generation

### 3.1 NEW thread table (this genuinely doesn't exist yet)
- `warmup_helper_thread` (or similarly-named, consistent with existing naming): `id`,
  `helper_id`, `cold_instance_id`, `topic_summary`, `step_count`,
  `status` (active/paused/done), `last_step_at`. One row per (helper, cold_instance) pair
  that has ever had an ask-step.

### 3.2 Generation (extends V28 PART 3's existing per-contact AI generation)
- Use the sender's CURRENT (`is_current=true`) `outreach_brief` as the seed.
- Generated ask-message: uses the contact's real full name; references job_title/
  years_experience/personal_benefit_note where relevant to explain personal relevance;
  continues the thread's `topic_summary` if `step_count > 0` (don't restart on an
  unrelated topic); on step 0, invents a natural, product-relevant opening (reuse the live
  Supabase pricing/product feed for a real product/price where it fits); includes wa.me
  link(s) for the 1–2 assigned cold accounts (never a raw number); passes V28's/V24's
  existing identifier-leak filter and text-similarity/anti-repeat check (reuse, don't
  reimplement).
- After generation, update `topic_summary`/`step_count` on the thread.

### 3.3 Tests
Generated messages include the real full name; reference job/benefit info when present;
continue an existing thread's topic on step 2+; never exceed 2 referenced cold accounts;
never leak identifiers; wa.me links correct; product/price grounding used when available;
existing V28 generation tests still pass.
Run full suite. Commit + push `V29 PART 3: conversation threads + thread-aware personalized generation`.

---

## PART 4 — Detection + thank-you (extend V28) + thread safety flagging

### 4.1 Detection + thank-you
- Confirm/extend V28's existing webhook-based detection (a contact's registered phone —
  primary OR `phone_secondary` — messaging a cold account) to also update the matching
  `warmup_helper_thread` (mark the current step done, record the incoming message).
- Confirm the existing thank-you send (from the contact's assigned sender) still fires
  correctly with the new thread-aware flow, gated/paced via `warmup_helper_engine`.

### 4.2 Thread safety flag (new)
- If a forbidden/sensitive word (reuse V26's keyword concept if present, else a small
  dedicated list) appears in either direction within a thread, set that
  `warmup_helper_thread.status = 'paused'` and create an admin alert — do not halt the
  whole feature, just that thread.

### 4.3 Tests
Detection correctly matches on either phone number and updates the thread; thank-you still
fires correctly; a forbidden-word occurrence pauses only that thread and creates an alert;
existing V28 detection/thank-you tests still pass.
Run full suite. Commit + push `V29 PART 4: thread-aware detection + thank-you + safety flagging`.

---

## PART 5 — Automatic AI-generated reply FROM the cold account (new capability)

### 5.1 Reply generation + send
- After PART 4 marks a step done, generate via the AI key pool ONE natural, contextual
  reply FROM the cold account back to the contact, continuing the thread's topic.
- **Gate this send through `can_send_now` for the COLD ACCOUNT** (via
  `warmup_helper_engine` — same rails, not a new path) — if the cold account is within its
  own 24h cooldown or otherwise unhealthy, defer the reply until eligible.
- Time the reply with a natural delay via the existing pacing/jitter constants — never
  instant.
- Apply the exact same identifier-leak filter to this reply text.
- Update the thread's `topic_summary`/`step_count` after the reply.

### 5.2 Tests
A completed step gets exactly one cold-account reply, timed with a natural delay; a cold
account still in cooldown defers its reply until eligible; the reply never leaks
identifiers; the thread topic updates correctly for future steps.
Run full suite. Commit + push `V29 PART 5: automatic contextual reply from the cold account`.

---

## PART 6 — Confirm/extend the single reminder (45–60 min) for the new thread flow

### 6.1 Reminder
- Confirm V28's existing reminder logic still correctly fires exactly once (45–60 min
  window) per ask-step under the new thread-aware model; if V28's reminder was tied to a
  different data shape, adapt it to work per `warmup_helper_thread`/step rather than
  duplicating reminder logic.

### 6.2 Tests
No completion within the window triggers exactly one reminder per step; a second reminder
never fires; completing after the reminder still correctly triggers the thank-you (PART 4)
and cold-account reply (PART 5).
Run full suite. Commit + push `V29 PART 6: confirm single reminder works with thread-aware flow`.

---

## PART 7 — Per-cold-account enrollment + automatic 10-day cycle

### 7.1 Enrollment
- Add/confirm a per-cold-account «عضویت در همکاری تیمی» toggle (distinct from mesh
  warm-up enrollment) with its own `enrolled_at`/`day_index` tracking.
- **Gate:** no ask-messages start for a cold account until its EXISTING 24h
  post-authorization cooldown (the same clock the mesh uses) has cleared.

### 7.2 10-day automatic schedule
- Automatically schedule ask-steps for that cold account's assigned contacts/threads
  across a 10-day window: conservative start (day 1–2: few steps), spreading further steps
  across remaining days — waking hours only, jittered, never two steps on the same thread
  on the same day. Fixed, non-user-configurable defaults, consistent with the mesh's own
  fixed schedule philosophy.

### 7.3 Tests
A cold account within its 24h cooldown gets no ask-sends; after cooldown, steps begin and
spread across the 10-day window; no thread gets two steps in one day.
Run full suite. Commit + push `V29 PART 7: per-cold-account enrollment + 10-day automatic cycle`.

---

## PART 8 — Sender warmth score/analysis (dashboard)

### 8.1 Score
- Compute a warmth score/level (کم/متوسط/بالا, or 0–100) for any instance considered as a
  «همکاری تیمی» sender (or mesh warm peer), extending V27 PART 3's binary ≥14-day/clean-
  history gate: factor in days since authorized, incident-free streak, recent activity.
  Show this on the sender-selection UI (PART 2) and the dashboard.

### 8.2 Tests
The score reflects age + incident history correctly; it displays on sender-selection and
dashboard. Run full suite. Commit + push `V29 PART 8: sender warmth score/analysis`.

---

## PART 9 — Dedicated «همکاری تیمی» log (Shamsi dates)

### 9.1 Log/table
- A dedicated page/table, separate from the existing inbox and send-queue, showing every
  event: from-account → to-account, message sent, message received (if any), event type
  (ask/reminder/thank-you/cold-reply), Shamsi date + exact time. Filter by sender, contact,
  or cold account. Reuse an existing Shamsi-date utility if one exists; add a small one if
  not.

### 9.2 Tests
The log correctly records/displays events with accurate Shamsi dates/times; filtering
works. Run full suite. Commit + push `V29 PART 9: dedicated Team Collaboration log (Shamsi dates)`.

---

## PART 10 — Final wiring, dashboard integration, cross-guardrail verification

### 10.1 Wiring
- Confirm every send path in this feature (ask, reminder, thank-you, cold-account reply)
  routes through `warmup_helper_engine`'s existing `can_send_now` + `peer_pacer` — no
  parallel/duplicate send path anywhere.
- Dashboard: per cold account, show «همکاری تیمی» enrollment status, day-in-cycle, active
  threads, paused/flagged threads; per sender, show warmth score + contact list summary +
  current brief.

### 10.2 Tests
Full end-to-end simulation: enroll a cold account → clear its cooldown (mock time) → first
ask-step generates, sends (gated/paced), gets "sent" via mock webhook → thank-you fires →
cold-account reply fires (gated on ITS cooldown/health) → thread topic updates → later step
continues the same topic → a missed step triggers exactly one reminder → forbidden-word
injection pauses only that thread. Re-run the FULL pre-existing suite (V17–V28, Telegram)
to confirm zero regressions.
Run full suite. Commit + push `V29 PART 10: final wiring + dashboard integration`.

---

## FINAL REPORT
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- Confirm no parallel/duplicate schema was created — everything extends V28's
  `warmup_helper`/`warmup_helper_task`/`outreach_brief`/`warmup_helper_engine`.
- Confirm each of the user's 15 points is addressed, one line each.
- Confirm the 3 stated design decisions and the 3 included suggestions, and how to
  disable/remove any if unwanted.
- Confirm: polling never enabled; ngrok/webhook untouched; mesh/V26/V27/Telegram code
  unchanged; every new send (sender AND cold-account sides) is gated/paced via the
  existing rails; full name mandatory going forward; no identifier leaks anywhere.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
Genuine two-way human traffic (real contacts + AI-personalized context + cold-account
replies) is a strong, legitimate warm-up signal. But it still involves real outbound sends
from both sender AND cold accounts, so all existing pacing/health-gate rules apply without
exception, and the 25–30-person scale should stay small and genuinely known/trusted.