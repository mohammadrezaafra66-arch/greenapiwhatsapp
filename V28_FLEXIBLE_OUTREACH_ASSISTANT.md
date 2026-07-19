# V28 MASTER PROMPT — Afrakala WhatsApp Sender
## Flexible multi-sender AI-personalized outreach assistant (generalizes V25's fixed-25 helper system)

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking questions and
> WITHOUT waiting for approval. After each PART: run a heavy test suite and verify it
> works; only advance once every test passes. Commit and push each PART separately.
> Produce a final report.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main
(`e660c90` — V26 group-monitoring, 7-part Telegram platform, and V27 anti-ban hardening
are all merged and deployed; 747 tests passing). Stack: FastAPI + PostgreSQL + Redis +
Celery + React/Vite, Green API gateway (webhook-only), multi-provider AI key pool.
Backend 8002, frontend 3002.

**Note — NOT part of this prompt:** temporarily pausing the automatic warm-up mesh needs
no new code — the existing "توقف همه" (stop all) button / per-account "توقف" button
already disables sending while preserving all enrollment data, so it can be re-enabled
later with "شروع گرم‌سازی همه". Do not build anything for that; it already exists.

**What this prompt builds:** V25 shipped a "human helpers" assist: a FIXED list of ≤25
known contacts, hard-capped, sending from the MAIN account only, with a semi-static
suggested message. The user now wants a more flexible, general version:

1. **Any of the user's own accounts can be the "outreach sender"** — not just the main
   account. The user picks which account sends.
2. **Each sender has its OWN contact list** (name + phone, name is MANDATORY), and the user
   assigns which cold number(s) that sender's contacts are asked to greet — per-sender
   lists, not one shared global list.
3. **No hard contact-count cap** (the user explicitly chose this). Instead: a non-blocking
   Persian soft-warning banner when a sender's list grows large (configurable threshold,
   default 30), so the user makes an informed choice rather than being blocked. The
   MANDATORY, non-configurable safety rail is PACING (see PART 4) — a large list simply
   takes longer to work through because sends stay slow and jittered; that pacing floor is
   the real protection here, not a count cap.
4. **AI-generated, personalized messages from a single short brief.** The user gives ONE
   short one-line brief per outreach batch (e.g. «بهش بگو به شماره‌های جدید ما سلام بده»).
   The AI generates a distinct, natural message PER CONTACT that MUST include that
   contact's real saved name (never a phone number or system label — reuse the V24
   identifier-leak safeguards) and must vary across contacts (reuse the existing
   text-similarity anti-repeat check).

Reuse V25's underlying mechanics wherever they still fit: the `warmup_helper` /
`warmup_helper_task` tables (generalized), the wa.me click-to-chat link, the webhook-based
"they actually sent it" detection, the auto thank-you, and the single 1-hour reminder.
Do not rebuild these from scratch — extend/generalize them.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only stays intact.
2. **Do NOT touch ngrok/webhook wiring, the WhatsApp send/mesh code, V27's anti-ban
   hardening, V26's group-monitoring, or the Telegram platform code.** This is additive.
3. **Only user-added known contacts** — never auto-import a phone's contact list, never
   message someone the user didn't explicitly add with a name.
4. **Pacing is HARD and non-configurable:** every outreach-ask message from a given sender
   must respect that sender's existing platform-appropriate delay/jitter (WhatsApp:
   10–15s+ floor per V27's constants; reuse them, don't invent new ones) and waking hours
   (09:00–21:00 Asia/Tehran). This applies regardless of list size — it is the real safety
   rail since there's no hard cap. Also apply V27 PART 1's live pre-send health gate to
   every outreach send (never send from an instance that's currently unhealthy/carded).
5. **Contact name is mandatory** at data-entry time (reject saving a contact with no
   name), and the AI-generated message MUST contain that real name — validate/regenerate
   if it's missing, mirroring how V24 validates messages must NOT contain account
   numbers/ids/labels.
6. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
7. **Commit + push each PART separately** (`V28 PART N: ...`).

### WORKFLOW PER PART
Explore existing V25 code first (`warmup_helper`, `warmup_helper_task`, the wa.me link
builder, the done-detection webhook branch, the thank-you/reminder logic) → generalize/
extend it → write/extend tests → run the FULL existing test suite → verify zero
regressions (especially V25's original behavior, V27's safety rails, and the mesh/campaign
paths) → commit + push → next PART.

---

## PART 1 — Generalize the data model (multi-sender, per-sender lists, no hard cap)

### 1.1 Schema changes (extend, don't replace, V25's tables)
- `warmup_helper`: add `sender_instance_id` (which of the user's OWN accounts this contact
  belongs to — replaces the old main-account-only assumption). `name` becomes NOT NULL
  (enforce at the DB/service layer — reject a save with no name, clear Persian error).
  Remove the hard 25-per-system cap; add a `soft_warning_threshold` config (default 30)
  used only to show a UI banner, never to block.
- `warmup_helper_task`: keep `helper_id` + `cold_instance_id` pairing (which cold number
  this contact is asked to greet); this already supports per-sender/per-contact assignment
  once `warmup_helper.sender_instance_id` exists.
- New `outreach_brief`: `id`, `sender_instance_id`, `brief_text` (the user's one-line
  instruction), `created_at` — stores the short brief used to seed AI generation for a
  batch of outreach tasks.
- Any instance can be chosen as an outreach sender (not restricted to the main account or
  to `is_warm_peer` instances) — this is a distinct role from mesh warm-peer status; do not
  conflate them, but DO still apply V27's live health gate before any send regardless of
  role.

### 1.2 Tests
Saving a helper with no name is rejected; a helper is correctly scoped to its
`sender_instance_id`; no hard cap blocks a large list; the soft-warning config is
retrievable; existing V25 data/behavior for previously-created helpers still works
(migrate old rows to a default sender_instance_id = the main account, so nothing breaks).
Run full suite. Commit + push `V28 PART 1: generalize helper schema (multi-sender, mandatory name, no hard cap)`.

---

## PART 2 — Sender selection + per-sender contact-list UI

### 2.1 UI
- A page/section «دستیار ارتباط شخصی‌سازی‌شده» (or similar) where the user:
  - Picks WHICH of their own accounts is the outreach sender (a dropdown of the user's
    instances — any of them, not restricted to warm peers).
  - Manages that sender's OWN contact list: add/edit/delete (name — required — + phone).
  - For each contact, assigns which cold number(s) they're asked to greet.
  - Sees a live count («۳۲ مخاطب») and, if over the soft threshold, a non-blocking Persian
    banner: «تعداد مخاطبان این فرستنده از حد معمول بیشتر است — چون سرعت ارسال محدود و
    ثابت است، ارسال به همه ممکن است چند روز طول بکشد. ادامه می‌دهید؟» (informational, with
    a simple acknowledge — never a hard block).
- Switching the sender dropdown shows/manages that sender's own separate list (lists don't
  mix between senders).

### 2.2 Tests
Selecting a sender shows only its own contacts; adding a contact without a name is
rejected in the UI/endpoint; exceeding the soft threshold shows the banner but still allows
saving/proceeding. Run full suite. Commit + push
`V28 PART 2: sender selection + per-sender contact-list UI`.

---

## PART 3 — AI-generated personalized messages from a one-line brief

### 3.1 Brief → per-contact generation
- The user enters ONE short brief for an outreach batch (e.g. «بهش بگو به شماره‌های جدید ما
  سلام بده»), tied to a sender (and optionally a specific cold number or set of cold
  numbers being introduced).
- For EACH contact in that batch, generate a DISTINCT message via the AI key pool that:
  - Naturally incorporates the brief's intent.
  - **MUST include that contact's real saved name** (e.g. «سلام رضا جان، ...»). Validate
    post-generation: if the name is missing, regenerate once, then fall back to a simple
    templated message that still inserts the real name (never send without the name).
  - **MUST NOT contain any account number/instance id/system label** — reuse the exact V24
    hard filter (reject ≥7-digit runs / known identifiers) before sending.
  - Includes the click-to-chat `wa.me/<coldNumberDigits>` link for the specific cold
    number this contact is being asked to greet (resolve the real phone via the existing
    phone-backfill/getWaSettings logic if needed, same as V25).
  - Optionally includes a short suggested line the contact can copy/paste (kept from V25's
    pattern), but the main message body around it should feel personal, not templated.
- Vary wording across contacts (reuse the existing text-similarity/anti-repeat check so two
  contacts of the same sender don't receive near-identical text).

### 3.2 Tests
- Generated messages for 10 different contacts all contain their own real name; none
  contain an account number/id/label (reuse V24's test fixtures/adversarial-leak approach);
  no two are near-duplicate text; the wa.me link matches the correct cold number.
- Missing-name detection triggers one regeneration attempt, then a safe templated fallback
  that still includes the name — never a send with no name.
Run full suite. Commit + push `V28 PART 3: AI-personalized per-contact messages from a one-line brief`.

---

## PART 4 — Sending mechanics: hard pacing + health gate (non-negotiable safety rail)

**Why this PART matters more than usual:** since there is no hard contact-count cap, this
pacing logic IS the safety rail. It must not be weakened or made configurable.

### 4.1 Enforce, per sender, regardless of list size
- Before each outreach-ask/reminder/thank-you send: (a) call V27 PART 1's `can_send_now`
  gate for the sender instance — skip/defer if not healthy; (b) enforce the sender's
  platform-appropriate minimum gap since its OWN last send (reuse V27 PART 2's peer-level
  pacing concept, applied here to the outreach-sender role too — a sender doing outreach
  asks and, say, mesh sends at the same time must still respect ONE shared per-instance
  pacer, not two independent ones that could interleave too fast).
- Waking hours only (09:00–21:00 Asia/Tehran), jittered.
- One ask + at most one reminder (1 hour later) per contact per cold number, exactly as
  V25 already does — keep this cap even though the CONTACT COUNT itself is uncapped.
- Because pacing is fixed and slow, a large contact list naturally spreads over many hours/
  days — document this clearly in code comments as the intended protective behavior.

### 4.2 Detection + thank-you (reuse V25)
- Keep V25's webhook-based "did the contact actually message the cold number" detection,
  and the automatic thank-you — generalized to work per (sender, contact, cold number)
  triple instead of assuming a single global helper pool.

### 4.3 Tests
- A sender with a large contact list (e.g. 50) has its sends verifiably spread across many
  hours (assert timestamps respect the pacing floor throughout, not just at the start).
- A sender doing BOTH mesh sends and outreach-ask sends at once never violates the shared
  per-instance pacing floor (no interleaved fast sends from the two features).
- An unhealthy/carded sender is blocked from outreach sends by the same V27 gate used for
  mesh/campaigns.
- Detection + thank-you + single-reminder behavior matches V25's existing tested behavior.
Run full suite. Commit + push `V28 PART 4: hard pacing + health gate for outreach sending`.

---

## PART 5 — Dashboard

### 5.1 Show per sender
- Contact count (+ soft-warning banner if over threshold), and per-contact task status
  (pending/asked/reminded/done), so the user can see who has greeted which cold number.
- Clear labeling that this sender role is separate from mesh warm-peer status (an account
  can be both, or either, independently).

### 5.2 Tests
Dashboard reports correct per-sender counts and task statuses. Run full suite. Commit +
push `V28 PART 5: outreach dashboard`.

---

## FINAL REPORT (after all parts)
- Test count before → after, per-PART deltas, "zero regressions" confirmed (re-run the
  FULL pre-existing suite, including V25/V26/V27/Telegram tests).
- Confirm: any account can be chosen as sender; per-sender contact lists work
  independently; name is mandatory and enforced; no hard cap exists but the soft-warning
  banner works; AI messages always include the real name and never leak identifiers; the
  hard pacing floor + V27 health gate are enforced regardless of list size; V25's original
  detection/thank-you/single-reminder behavior is preserved (generalized, not weakened).
- Confirm: polling never enabled; ngrok/webhook untouched; mesh/campaign/V27/V26/Telegram
  code unchanged.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
Removing the hard contact-count cap shifts ALL of the safety burden onto pacing and the
live health gate — both must stay hard-coded and non-configurable. A large contact list
for one sender is not inherently unsafe as long as sends stay slow, jittered, and
waking-hours-only; but the user should still exercise judgment about how many real people
to involve at once, since the sending account is still doing outbound activity and remains
subject to the same anti-ban realities as any other WhatsApp sender.