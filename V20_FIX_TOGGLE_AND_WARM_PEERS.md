# V20 MASTER PROMPT — Afrakala WhatsApp Sender
## Fix stuck warm-up toggle + make existing warm accounts usable as mesh PEERS

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking the user
> questions and WITHOUT waiting for approval. After each PART: run a heavy test suite and
> verify it works; only advance once every test passes. Commit and push each PART
> separately. Produce a final report at the end.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: **V19**, all tests
passing, `origin/main` clean. Frontend was just redeployed and now shows the V17/V18
"گرم‌سازی هوشمند" wording correctly.

A diagnostic surfaced THREE issues to fix:

1. **The smart-warmup checkbox is STUCK ON and cannot be unchecked** for accounts that
   have a legacy `auto_warmup=true` flag but no enrollment. Root cause: the disable path
   (`disable_warmup`) skips `db.commit()` in its no-enrollment branch, so the endpoint's
   `auto_warmup=False` is rolled back by `get_db`. The frontend then re-checks the box
   because its binding is `checked = warmup_enrolled || auto_warmup`. Affects 5 accounts
   currently: `7105325764`, `770022683810`, `770022683809`, `770022682898`, `770022682882`.

2. **Existing warm accounts are NOT usable as mesh peers.** The 2 enrolled cold numbers
   (`770022683837`, `770022683838`) are in COOLDOWN but have **0 mesh edges and no eligible
   peer** — because peer eligibility currently requires a GRADUATED enrollment, and the
   main warm account `7105325764` (11 active days, already warm from real use) never went
   through warm-up, so `is_warm_peer=false`. Result: even after cooldown, the mesh has
   nobody to send from. We need a way to mark an already-warm account as a **PEER** without
   enrolling it in warm-up.

3. **Stale flags:** the 5 legacy `auto_warmup=true` flags should be reconciled.

**User decision (build to this):** the main warm account `7105325764` should act **ONLY as
a PEER** (it sends warm-up messages TO cold numbers) and must **NEVER be warmed itself** (no
enrollment, no risk to it). "Peer" and "being warmed" are DIFFERENT roles — keep them
separate.

**Stack:** FastAPI + PostgreSQL + Redis + Celery + React/Vite, Green API gateway, AI key
pool. Backend 8002, frontend 3002. Webhook-only.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only.
2. **Do NOT touch ngrok / webhook wiring. Do NOT weaken the send path, the V17 message
   mesh, or the V19 group track.**
3. **Warm-up stays OFF by default.** A peer designation must NOT start warming that peer.
4. **Mesh/peers only message the user's own instances, only over mutual-contact edges.
   Never a stranger.**
5. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
6. **Commit + push each PART separately** (`V20 PART N: ...`).

### WORKFLOW PER PART
Explore existing code first → implement → write/extend tests → run FULL `pytest` → verify →
commit + push → next PART.

---

## PART 1 — Fix the stuck toggle (disable path must persist; frontend must reflect enrollment)

**Why:** The user cannot turn smart warm-up OFF. This is a real bug.

### 1.1 Backend
- Fix the disable path so it ALWAYS persists: ensure `disable_warmup` (and/or
  `set_auto_warmup`) commits in EVERY branch, including the no-enrollment branch, so
  `auto_warmup=False` is saved and not rolled back by `get_db`. Verify the whole
  enable→disable→enable cycle persists correctly.
- Confirm the enable path still works (V18) and disabling actually disables any enrollment.

### 1.2 Frontend
- Change the checkbox binding so it reflects the REAL warm-up state, not the legacy flag:
  `checked = !!warmup_enrolled` (drop the `|| auto_warmup` fallback). The box must follow
  enrollment/enabled state so a successful disable stays unchecked after refresh.

### 1.3 One-time reconcile of stale flags
- Clear the 5 stale `auto_warmup=true` flags that have no enrollment
  (`7105325764`, `770022683810`, `770022683809`, `770022682898`, `770022682882`). Do this
  as a safe, idempotent data reconcile (e.g. a migration or a guarded startup fix): set
  `auto_warmup=false` where there is no active `warmup_enrollment`. Must not touch any
  account that has a real active enrollment.

### 1.4 Tests
- Toggle OFF persists across a simulated refresh (auto_warmup=false stays false; box stays
  unchecked). Enable→disable→enable cycle works and commits each time.
- Frontend binding: box checked iff enrolled/enabled (not driven by the legacy flag).
- Reconcile clears only flags with no enrollment; leaves enrolled accounts untouched.
Run full suite. Commit + push `V20 PART 1: fix stuck warm-up toggle (persist disable + enrollment-based checkbox + clear stale flags)`.

---

## PART 2 — Warm PEER designation (separate from being warmed)

**Why:** The mesh needs senders. An already-warm account must be usable as a PEER that
sends warm-up messages to cold numbers, WITHOUT being enrolled/warmed itself.

### 2.1 Model + eligibility
- Introduce an explicit **warm-peer** concept: an instance can be marked
  `is_warm_peer=true` (a durable per-instance flag/setting) meaning "this account is
  already warm and may be used as a mesh sender." This is INDEPENDENT of warm-up
  enrollment — a peer has NO `warmup_enrollment` and is NEVER put through warm-up stages.
- Update mesh peer-eligibility so eligible peers = instances that are **GRADUATED**
  (from warm-up) **OR** explicitly marked `is_warm_peer=true`. Both are valid senders.
- A warm peer must NEVER be enrolled as a cold number by any automatic process. Enabling
  peer status must not create an enrollment and must not start warming it. Guard against a
  peer ever appearing on the "being warmed" side.

### 2.2 UI
- On the accounts page (and/or the smart-warmup page), add a clear, separate control per
  account, e.g. a toggle/badge **«اکانت گرم مرجع (فرستنده گرم‌سازی)»** with a short Persian
  explanation: turning it on means this already-warm account will be used to SEND warm-up
  messages to new accounts, and it will NOT be warmed itself / not put at risk.
- Make the two roles visually distinct so the user never confuses "این اکانت گرم می‌شود"
  (being warmed) with "این اکانت گرم‌کننده است" (a peer/sender).
- Default: mark `7105325764` as a warm peer is a USER action (the user will toggle it);
  do not auto-mark anything. Ship the control OFF by default.

### 2.3 Wire peers into the existing mesh (no other changes)
- The V17 mesh scheduler, when a cold number reaches the sending stages, must now be able
  to pick from eligible peers (GRADUATED or `is_warm_peer`) to build edges and send. This
  fixes the "0 edges / no peer" situation: once the user marks `7105325764` as a warm peer,
  the 2 enrolled cold numbers get a real sender after cooldown.
- Do NOT change mesh cadence, caps, jitter, mutual-contact handshake, or kill-switches —
  only broaden who counts as an eligible peer. Assert mesh timing is otherwise unchanged.

### 2.4 Tests
- An instance marked `is_warm_peer=true` becomes an eligible mesh peer WITHOUT any
  enrollment and is never enrolled/warmed by automation.
- With a warm peer available, an enrolled cold number builds mesh edges to it and (after
  cooldown, in tests with simulated time) the mesh has a valid sender (fixes 0-edge case).
- A warm peer is never placed on the "being warmed" side; toggling peer status does not
  create an enrollment.
- GRADUATED instances remain eligible peers too. Mesh cadence/caps unchanged.
- Nothing here enables polling; no stranger is messaged.
Run full suite. Commit + push `V20 PART 2: warm-peer designation (sender role separate from being warmed)`.

---

## PART 3 — Dashboard clarity + safety confirmation

### 3.1 Dashboard
- On the warm-up dashboard, clearly show, per account, its ROLE: "در حال گرم‌سازی"
  (being warmed, with its state/day) vs "اکانت گرم مرجع / فرستنده" (a peer/sender) vs
  neither. For enrolled cold numbers, show which peer(s) they are being warmed by (edges).
- Show a clear notice if an enrolled cold number has NO eligible peer yet
  («هیچ اکانت گرم مرجعی انتخاب نشده — یک اکانت گرم را به‌عنوان فرستنده علامت بزنید»), so the
  0-peer situation is visible instead of silent.

### 3.2 Tests
- Dashboard reports correct role per account and the no-peer notice when applicable. Run
  full suite. Commit + push `V20 PART 3: dashboard roles + no-peer notice`.

---

## FINAL REPORT (after all parts)
Produce one summary with:
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- PART 1: the toggle bug root cause and fix; confirmation the checkbox can now be turned
  OFF and stays off after refresh; the 5 stale flags reconciled.
- PART 2: how warm-peer designation works, that peers are senders only and never warmed,
  and that marking `7105325764` as a peer gives the 2 COOLDOWN cold numbers a real sender.
- PART 3: dashboard now shows roles + the no-peer notice.
- **Plain answer:** after V20, to actually run the mesh the user should mark `7105325764`
  as a warm peer (sender); it will send warm-up messages to enrolled cold numbers and will
  NOT be warmed/enrolled itself.
- Confirmation: polling never enabled; ngrok/webhook untouched; message mesh + group track
  unchanged except broadened peer eligibility; warm-up OFF by default; peers never warmed;
  no strangers messaged.
- The list of pushed commits.

Then STOP and await the user's review.

---
### REALITY NOTE (short version in the report)
The peer account sends warm-up messages but is not itself put at risk. Still, warm-up
reduces ban risk without eliminating it, and fresh numbers can be carded within minutes of
connecting. Warm-test with LOW-VALUE cold numbers first; keep the 24h cooldown, waking
hours, and slow pace permanently.