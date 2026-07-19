# V19 MASTER PROMPT — Afrakala WhatsApp Sender
## Group-based warm-up: add cold numbers to admin-owned groups (ADD to the mesh, don't replace it)

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking the user
> questions and WITHOUT waiting for approval. After each PART: run a heavy test suite and
> verify it works; only advance once every test passes. Commit and push each PART
> separately. Produce a final report at the end.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: **V18** (fan-out fix +
toggle→mesh wiring). All tests passing, `origin/main` clean.

**What V19 adds:** a group-based warm-up that helps COLD (new) numbers warm up by placing
them into high-traffic WhatsApp GROUPS, so they receive natural incoming messages. This is
an **ADDITION** to the existing V17 message-based mesh — the mesh must NOT be reduced,
weakened, or replaced. Everything is driven by the SAME single "🔥 گرم‌سازی هوشمند"
toggle and runs fully automatically.

**Stack:** FastAPI + PostgreSQL + Redis + Celery + React/Vite, Green API gateway, AI key
pool. Backend 8002, frontend 3002. Multiple Green API instances (some warm/authorized,
some cold/new). Webhook mode ONLY.

### CRITICAL RESEARCH FINDINGS (ground truth — build to these)

Green API's group methods are exactly: CreateGroup, UpdateGroupName, GetGroupData,
UpdateGroupSettings, AddGroupParticipant, RemoveGroupParticipant, SetGroupAdmin,
RemoveAdmin, SetGroupPicture, LeaveGroup. There is **NO join-by-invite-link method.**

- **PART A — add cold numbers to admin-owned groups: SUPPORTED.** Flow:
  1. List a warm account's groups: `GET /waInstance{id}/getContacts/{token}?group=true`
     — groups have `"type":"group"` and an `id` ending in `@g.us`. (If the data array is
     empty, retry the call — documented behavior.)
  2. For each group, `POST /waInstance{id}/getGroupData/{token}` body
     `{"groupId":"...@g.us"}` → returns `owner`, `subject`, `size`, `groupInviteLink`,
     and a `participants[]` array where each item has `id`, `isAdmin`, `isSuperAdmin`.
     **The warm account can add members to a group ONLY if its own number (`<number>@c.us`)
     appears in `participants` with `isAdmin==true` OR `isSuperAdmin==true`.** Filter to
     exactly those groups. (Throttle GetGroupData — calling it too often makes WhatsApp
     temporarily return an empty `groupInviteLink`, and excessive polling is a mild risk
     signal. Cache results.)
  3. Add: `POST /waInstance{id}/addGroupParticipant/{token}` body
     `{"groupId":"...@g.us","participantChatId":"<coldNumber>@c.us"}` → returns
     `{"addParticipant": true|false}`. `false` happens if: the instance is not admin of
     that group, the participant number is NOT in the instance's phonebook, or the contact
     is already a member. **Therefore, before adding, MUST save the cold number as a
     CONTACT on the warm (admin) instance via AddContact** (ideally mutual). Because the
     cold accounts are the user's OWN numbers, this is legitimate and makes adds succeed.

- **PART B — auto-join public groups via invite link: NOT POSSIBLE via Green API.** No
  JoinGroup/AcceptInvite method exists; sending a chat.whatsapp.com link via SendMessage
  does not join. So PART B becomes a **manual link vault**: store links + group names +
  notes; the system does NOT auto-join. Surface a clear Persian note that joining these
  must be done by hand on the phone. If Green API ever adds a join method, this becomes
  automatable later. (Do NOT try to fake it or auto-send invite links as a workaround.)

### Group ban signals & fixed anti-ban schedule (from research — implement EXACTLY)

WhatsApp flags fresh numbers doing group actions: adding non-contacts, joining/adding to
many groups quickly, acting as admin immediately, "you've created too many groups
recently", inability to add members, linked-device disconnect. Green API: a new number
must warm ≥10 days; "in the first 10 days it is not recommended to send messages via
Instance and to create groups"; simulate human work; group creation no more than 1 per 5
min. Group size cap is 1,024.

**FIXED, standards-based group-action schedule (NOT user-configurable — ship these):**
- **Day 0 (registration) & Day 1 (auth / COOLDOWN):** ZERO group actions.
- **Days 2–3 (RECEIVING):** ZERO group actions (mesh receiving continues).
- **Day 4 (REPLYING begins):** first group action allowed — add the cold number to **1**
  admin group, waking hours only (09:00–21:00 Asia/Tehran) with random jitter.
- **Days 5–10 (RAMPING):** at most **1 group action per day**, and **no more than 5 total
  group memberships across the whole first 10 days.** Space consecutive group actions
  ≥48h apart where possible.
- **Day 10+ (MATURING):** slow to **~1 group every 3–10 days.**
- **Global caps (always):** never more than **1 group action per cold number per day**;
  minimum **24h (target 48h) between any two group actions** for the same cold number;
  waking hours only; randomized timing; ALWAYS mutual-contact-save before an add.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only. Group-action results/errors and state
   changes come via webhooks and the AddGroupParticipant response.
2. **Do NOT touch ngrok / webhook wiring. Do NOT weaken the send path or the V17 mesh.**
   The message-based mesh keeps running unchanged; group warm-up is purely additive.
3. **Only operate on the user's OWN groups/instances.** Cold numbers added are the user's
   own accounts. Never add third-party strangers to groups. Never message strangers.
4. **Warm-up (incl. group warm-up) is OFF by default;** everything triggers from the one
   toggle. Group adds happen only when the user has explicitly selected target groups.
5. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
6. **Commit + push each PART separately** (`V19 PART N: ...`).

### WORKFLOW PER PART
Explore existing code first → implement → write/extend tests (mock Green API HTTP) → run
FULL `pytest` → verify → commit + push → next PART. If something needs a live second
instance/real group, implement fully against mocked Green API responses and note it under
"NEEDS LIVE TEST".

---

## PART 1 — Read a warm account's admin groups (backend + API)

**Why:** The UI must show ONLY groups where the selected warm account can add members.

### 1.1 Backend
- Add a service that, given a warm instance, calls `getContacts?group=true`, then
  `getGroupData` per group (throttled + cached, e.g. cache per group for a sensible TTL),
  and returns only groups where that instance's own number has `isAdmin` or `isSuperAdmin`.
  Return per group: `groupId`, `subject` (name), `size` (member count), and admin flag.
  Handle the documented empty-array retry for getContacts.
- Endpoint (Persian-facing UI will call it): "list admin groups for warm instance X".
- Respect a throttle so GetGroupData isn't hammered (protect against the empty-invite-link
  penalty and risk signal).

### 1.2 Tests
Mock Green API HTTP. Assert: only admin/superadmin groups returned; non-admin groups
filtered out; empty-array retry works; cache/throttle works. Run full suite. Commit + push
`V19 PART 1: read warm account admin groups`.

---

## PART 2 — Data model for group warm-up + the manual link vault

### 2.1 Schema (PostgreSQL, existing migration style)
- `warmup_group_target`: `id`, `warm_instance_id` (the admin account),
  `group_id` (`...@g.us`), `group_subject`, `is_selected` (bool), `created_at`.
  These are the admin-owned groups the user selected as destinations for cold numbers.
- `warmup_group_membership`: `id`, `cold_instance_id`, `warm_instance_id`, `group_id`,
  `status` (pending/added/failed/skipped), `attempts`, `last_attempt_at`, `added_at`,
  `error_reason`, `created_at`. Tracks each cold→group placement.
- `warmup_link_vault`: `id`, `group_name`, `invite_link`, `notes`, `created_at`. The
  MANUAL vault for PART B (public groups we're not admin of). Data only — no auto-join.

### 2.2 Tests
Migrations apply; basic CRUD on the three tables. Run full suite. Commit + push
`V19 PART 2: group warm-up schema + link vault`.

---

## PART 3 — Group warm-up UI in the smart-warmup page (Persian, RTL)

**Why:** The user selects a warm account, sees its admin groups, and picks targets; plus a
separate manual link-vault area.

### 3.1 «افزودن به گروه‌های اکانت گرم» (admin-owned groups)
- The user first selects one of their WARM accounts (dropdown of warm/graduated instances).
- On selection, call PART 1's endpoint and show ONLY that account's admin groups, each with
  name + member count + a checkbox. Selecting groups writes `warmup_group_target` rows
  (`is_selected=true`). Show a short Persian helper: these groups will be used to place cold
  numbers into, slowly and automatically, once smart warm-up is on.
- Show a loading state and an empty state («این اکانت در هیچ گروهی ادمین نیست»).

### 3.2 «مخزن لینک گروه‌ها (عضویت دستی)» (manual link vault — PART B)
- A separate section to add/edit/delete entries: group name + invite link + notes
  (`warmup_link_vault`).
- Show a clear Persian notice, e.g.
  **«توجه: عضویت در این گروه‌ها فقط به‌صورت دستی روی گوشی ممکن است — Green API اجازه‌ی عضویت خودکار با لینک را نمی‌دهد. این لینک‌ها اینجا ذخیره می‌شوند تا پرسنل دستی عضو شوند.»**
- Do NOT wire any auto-join. This is a saved list + reminder only.

### 3.3 Tests
Endpoint/UI data tests: selecting a warm account returns its admin groups; selecting groups
persists targets; empty state; link-vault CRUD. Run full suite. Commit + push
`V19 PART 3: group warm-up UI + manual link vault`.

---

## PART 4 — Automatic group-placement scheduler (fixed anti-ban schedule)

**Why:** This is the engine that, when smart warm-up is ON, automatically adds cold numbers
into the selected admin groups on the fixed, conservative schedule — WITHOUT touching the
message mesh.

### 4.1 Scheduler
- Extend the existing warm-up Celery scheduling. For each cold number that is ENROLLED
  (V17) and whose owner has selected group targets, drive group placements per the FIXED
  schedule above, keyed off the number's warm-up state/day_index:
  COOLDOWN/RECEIVING → no group actions; REPLYING (Day 4) → first group; RAMPING (5–10) →
  ≤1/day and ≤5 total in first 10 days, ≥48h spacing; MATURING (10+) → ~1 per 3–10 days.
- Enforce global caps: ≤1 group action per cold number per day; ≥24h (target 48h) between
  actions; waking hours 09:00–21:00 Asia/Tehran with jitter; never two groups in one
  session.
- **This runs IN ADDITION to the message mesh.** The mesh scheduler is not modified or
  slowed; group placement is a separate, parallel track under the same enrollment.

### 4.2 Placement procedure (per group action)
1. Pick the next selected target group for this cold number (that it isn't already in /
   pending), whose `warm_instance_id` is authorized/healthy and still admin (re-verify via
   cached GetGroupData; refresh if stale).
2. **Save contacts mutually**: warm(admin) instance saves the cold number via AddContact;
   ideally cold saves warm too. (Required for AddParticipant to succeed.)
3. Call `AddGroupParticipant` from the WARM admin instance with the cold number.
4. Read `addParticipant`. If `true` → mark membership `added`. If `false` → save contact
   again + retry once; if still false, mark `failed` with `error_reason`, back off, and do
   NOT keep hammering.
5. Log every action (instance, group, result, timestamp).

### 4.3 Safety / kill-switch (reuse + extend V17)
Immediately halt ALL group actions for a cold number (and alert) if: AddGroupParticipant
returns false repeatedly; the instance state ≠ `authorized` / device disconnect; any
"too many groups"/add-restriction signal; or the existing V17 mesh kill-switch fires
(yellowCard/blocked). On block → reset warm-up to zero (as V17 does). If a WARM admin
instance itself shows trouble, stop using it as a group source.

### 4.4 Tests (biggest surface — mock Green API + simulate time)
Assert:
- No group action during COOLDOWN/RECEIVING; first action only at Day 4 (REPLYING).
- ≤1 group action/cold-number/day; ≤5 total memberships in first 10 days; ≥48h spacing;
  actions only in waking hours; never 2 groups in one session; Day 10+ slows to ~1/3–10d.
- Mutual contact save happens before AddParticipant; on `false`, one retry after re-save,
  then failure is recorded without a hammer loop.
- The message-based mesh schedule is UNCHANGED when group warm-up runs (assert mesh
  cadence/counts identical with and without group targets).
- yellowCard/block halts group actions and resets per V17; a troubled warm source is
  dropped.
- Nothing here enables polling; no stranger is added.
Run full suite. Commit + push `V19 PART 4: automatic group-placement scheduler (fixed anti-ban schedule)`.

---

## PART 5 — Dashboard surfacing + final wiring

### 5.1 Dashboard
Extend the warm-up dashboard: per cold number, show group placements (which groups, status
added/pending/failed, next scheduled group action time) alongside the existing mesh info.
Show the manual link-vault list with the "join by hand" reminder. Persian, RTL.

### 5.2 One-toggle confirmation
Confirm the single "🔥 گرم‌سازی هوشمند" toggle now drives BOTH tracks automatically: the
V17 message mesh AND the V19 group placement (when group targets are selected). Nothing
extra for the user to press.

### 5.3 Tests
Dashboard endpoint returns correct group-placement state; toggle drives both tracks. Run
full suite. Commit + push `V19 PART 5: dashboard + one-toggle wiring`.

---

## FINAL REPORT (after all parts)
Produce one summary with:
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- One line per PART (done / done-with-caveat) and what was built.
- **Plainly state:** PART A (adding cold numbers to admin-owned groups) is fully automated;
  PART B (public-group invite links) is a MANUAL vault because Green API cannot join by
  link — and what the user must do by hand.
- The exact fixed schedule shipped (Day-by-day + global caps).
- **NEEDS LIVE TEST:** real AddGroupParticipant against a real admin group + a real cold
  number (only verifiable live).
- **NEEDS USER ACTION:** to use group warm-up, the user must (a) have ≥1 warm account that
  is ADMIN in some groups, (b) select target groups in the UI; and must manually join the
  link-vault groups on the phone.
- Confirmation: polling never enabled; ngrok/webhook untouched; the V17 message mesh is
  unchanged (not reduced); group warm-up is additive; warm-up OFF by default; only the
  user's own numbers/groups are touched; no strangers added.
- The list of pushed commits.

Then STOP and await the user's review.

---
### REALITY NOTE (short version in the report)
Group actions on fresh numbers are themselves a ban signal — adding to groups too fast, or
a brand-new number doing group actions, gets numbers carded/banned (a fresh number was
carded within minutes in a prior incident, before we sent anything). The fixed, slow
schedule reduces this risk but does not remove it. Warm-test on LOW-VALUE numbers first,
and keep the 24h-after-auth + waking-hours + slow-pace rules permanently.