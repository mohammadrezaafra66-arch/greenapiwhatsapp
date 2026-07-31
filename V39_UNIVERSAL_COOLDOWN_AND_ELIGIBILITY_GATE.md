# V39 MASTER PROMPT — Afrakala WhatsApp Sender
## Two permanent, system-enforced rules: universal connect-cooldown + hard sender-eligibility gate (with logged override)

> **MODE: FULLY AUTONOMOUS, RESUMABLE ACROSS SESSION LIMITS.** Execute every PART
> end-to-end WITHOUT asking questions and WITHOUT waiting for approval. After each PART:
> run a heavy test suite and verify it works; only advance once every test passes. Commit
> and push each PART separately. If you hit a usage/session limit mid-part, stop cleanly;
> on the next invocation, run `git log --oneline -15` first and resume from the next
> incomplete PART rather than restarting.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main — V17 through
V38 are merged (mesh, V27 anti-ban, Telegram, V28-V38 «همکاری تیمی» / Team Collaboration,
the recent reconnect-stamp + 24h TC-only rest mechanism, the auto-reroute pause hotfix).

**Why this prompt exists:** Over the last day, the team manually re-derived and re-checked
(via ad-hoc diagnostics) two safety rules that this project has relied on informally since
its early research phase: (1) never send from an account within 24h of it connecting/
reconnecting to Green API, and (2) never use an account younger than 14 days (with a clean
incident history) as a Team Collaboration sender. Both rules already exist informally —
the 24h rest is coded but ONLY for Team Collaboration sends (`reconnect_rest_active` in
`warmup_helper_engine.py`, called only from `_send_from_main`); the 14-day rule exists only
as a DISPLAYED warmth score/flag (V30 PART 8), not an enforced constraint — nothing
currently stops assigning or using a too-young account as a sender. **This prompt makes
both rules permanent, universal, system-enforced guardrails so they never again require a
manual diagnostic to verify.**

**Design decisions (already made by the user, implement exactly):**
- The 24h connect/reconnect cooldown must become UNIVERSAL: it applies to EVERY account
  (not just the ones we've been manually managing), on BOTH a brand-new account's first-
  ever connection AND any later reconnection, and it must block ALL outbound send paths
  (mesh warm-up, campaigns, Team Collaboration) — not just Team Collaboration as it is
  today. This explicitly supersedes the earlier narrower "TC-only" scoping decision.
- The 14-day + clean-incident-history bar for the Team Collaboration SENDER role becomes a
  HARD gate — but with an explicit, deliberate override: a user can still assign/use a
  too-young account as a sender ONLY by consciously confirming an override (a clear risk
  warning + a required short note), and every such override MUST be logged (who/when/which
  account/why) so it's auditable later.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only stays intact.
2. **Do NOT touch ngrok/webhook wiring.** Do not weaken any EXISTING health/incident
   detection in V27 — this prompt ADDS a new universal constraint on top, it does not
   remove or loosen anything currently blocking an unhealthy account.
3. **Grandfather existing long-running accounts.** An account with no stamped
   `connected_at`/`reconnected_at` (because it connected before this stamping mechanism
   existed) must NOT suddenly become blocked by the new universal cooldown — treat a NULL
   timestamp as "long enough ago" (not blocking), never as "just connected." Verify this
   explicitly with a test before considering PART 1 done.
4. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
5. **Commit + push each PART separately** (`V39 PART N: ...`).

### WORKFLOW PER PART
Explore the ACTUAL current code first (`warmup_helper_engine.py`'s `reconnect_rest_active`
+ its 4 stamping call-sites, V27's `can_send_now`/`gate_check`, V30 PART 8's warmth/
eligibility computation, `warmup_sender_config` or equivalent) → extend/consolidate,
don't duplicate → write/extend tests → run the FULL existing test suite → verify zero
regressions → commit + push → next PART.

---

## PART 1 — Universal connect/reconnect 24h cooldown (all accounts, all send paths)

### 1.1 Stamping coverage
- Confirm (or fix) that the SAME stamping mechanism fires on a brand-new account's very
  first-ever transition to `active`/authorized, not only on a `disconnected → active`
  reconnect. Use one consistent field name (rename/generalize if the current field is
  named in a reconnect-specific way) that means "the last moment this account became
  connected, whether for the first time or after a disconnect."
- Grandfather clause: for any account where this timestamp is NULL/unset (pre-existing,
  long-running accounts from before this mechanism existed), the cooldown must NOT apply —
  treat NULL as compliant, never as "just connected."

### 1.2 Move the gate into the SHARED can_send_now (V27)
- Fold the 24h floor into `can_send_now`/`gate_check` (V27's shared gate used by every
  send path) rather than leaving it as a Team-Collaboration-only special case in
  `_send_from_main`. Consolidate — don't keep two parallel implementations of the same
  check; if `reconnect_rest_active` becomes a thin wrapper around the shared gate's logic
  (or is removed in favor of calling the shared gate directly), that's fine, but there
  must be exactly ONE source of truth for "is this account past its connect-cooldown."
- Confirm mesh (`warmup_engine.execute_action` → its gate check) and campaigns
  (`campaign_runner._deliver_message`) now ALSO respect this 24h floor, in addition to
  Team Collaboration.

### 1.3 Tests
A brand-new account (first-ever connection, no prior history) cannot send via ANY path
(mesh, campaign, Team Collaboration) for the first 24h, then becomes eligible exactly at
the boundary. A reconnecting account behaves identically. An account with a NULL
connect-timestamp (simulating a pre-existing account) is NOT blocked. All three send paths
share one underlying check (assert via code inspection or a shared-function test that
there isn't a second, divergent implementation).
Run full suite. Commit + push `V39 PART 1: universal 24h connect-cooldown across all send paths`.

---

## PART 2 — Hard 14-day + clean-history sender-eligibility gate (assignment time)

### 2.1 Reuse the existing eligibility computation
- Reuse V27 PART 3 / V30 PART 8's existing ≥14-day-authorized + clean-incident-history
  computation (don't reimplement it) as the authoritative "is this account eligible to be
  a Team Collaboration sender" check.

### 2.2 Enforce at assignment
- Wherever a `sender_instance_id` is assigned to a `warmup_helper` contact (or a sender is
  otherwise designated), check eligibility. If ineligible and no override is present in the
  request: reject with a clear Persian error stating the EXACT reason (e.g., "این اکانت
  فقط ۶.۹ روز از اتصالش گذشته — حداقل ۱۴ روز لازم است" or "این اکانت در ۱۴ روز اخیر حادثه
  داشته است") — not a generic message.
- If an explicit override is present (a boolean flag + a required short text note): allow
  the assignment, and PERSIST the override (extend `warmup_sender_config` or equivalent
  with `eligibility_overridden_at` + `eligibility_override_note` + who/when), so later
  checks (PART 3) know this sender was deliberately approved despite being under-eligible.
  Also write an entry to the existing Team Collaboration log (`warmup_helper_log` or the
  dedicated log table) recording the override event for auditability.

### 2.3 Tests
Assigning an eligible (≥14-day, clean) account succeeds with no override needed. Assigning
an ineligible account without an override is rejected with a specific, accurate Persian
error. Assigning an ineligible account WITH an override succeeds, persists the override
record, and writes an auditable log entry.
Run full suite. Commit + push `V39 PART 2: hard sender-eligibility gate with logged override`.

---

## PART 3 — Send-time defense-in-depth (in case of a legacy/bypassed assignment)

### 3.1 Enforce again at actual send time
- In `_send_from_main` (and/or the shared gate, whichever is architecturally cleaner —
  investigate and pick one, don't duplicate), before sending FROM a given sender instance,
  check: is this sender currently eligible (≥14-day + clean), OR does it have a valid
  logged override (from PART 2)? If neither, block the send (this only matters for data
  that bypassed the PART 2 API check — e.g., a direct DB edit or a pre-V39 legacy
  assignment) — do not silently allow it.

### 3.2 Tests
A sender assigned before V39 existed (simulating legacy data with no override record) and
that fails the eligibility check is blocked from sending until either it ages past 14 days
clean, or an override is explicitly recorded for it. An eligible sender, or one with a
valid override, sends normally.
Run full suite. Commit + push `V39 PART 3: send-time defense-in-depth for sender eligibility`.

---

## PART 4 — Frontend: clear warning/confirmation UI for the override

### 4.1 UI
- When the user tries to select/assign an ineligible account as a sender in
  `/team-collaboration`, show a clear Persian warning dialog stating the exact reason
  (days remaining / incident history), require an explicit confirmation checkbox
  (e.g., «می‌دانم این اکانت هنوز آماده نیست و مسئولیت ریسک را می‌پذیرم») and a short
  required note field, before the assignment can be submitted with the override.
- Show a visible «رد شرط ۱۴روزه» (override) badge next to any sender currently running on
  an overridden basis, so the user can see at a glance which senders are non-compliant by
  deliberate choice.

### 4.2 Tests
The UI blocks submission of an ineligible-sender assignment without the confirmation
checkbox + note; submits correctly once both are provided; the override badge displays
correctly for an overridden sender.
Run full suite (backend) + frontend build/pure-module tests. Commit + push
`V39 PART 4: frontend warning/confirmation UI for sender-eligibility override`.

---

## PART 5 — Final wiring + full regression pass

### 5.1 Wiring
- Confirm every send path (mesh, campaigns, Team Collaboration ask/reminder/thank-you/
  cold-reply) now honors BOTH: the universal 24h connect-cooldown (PART 1) and, for Team
  Collaboration specifically, the sender-eligibility gate with override (PARTs 2-3).
- Confirm grandfathering still holds for all currently-running accounts (re-run PART 1's
  NULL-timestamp test against the live accounts list as a sanity check, read-only).

### 5.2 Tests
Full end-to-end simulation: a brand-new account connects → blocked everywhere for 24h →
becomes eligible for general sending, but STILL blocked from the sender role until 14
clean days OR an explicit override; an override is applied → sends proceed, logged.
Re-run the FULL pre-existing suite (V17–V38) to confirm zero regressions.
Run full suite. Commit + push `V39 PART 5: final wiring + full regression pass`.

---

## FINAL REPORT
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- Confirm: the 24h connect-cooldown is now universal (all send paths, all accounts, first-
  connection AND reconnection), with existing long-running accounts correctly grandfathered
  (list which currently-active accounts, if any, were verified NULL-timestamp/unaffected).
- Confirm: the 14-day sender-eligibility gate is now a hard, enforced constraint (not just
  a displayed score), with a working, logged, explicit-override escape hatch.
- Confirm: polling never enabled; ngrok/webhook untouched; no existing V27 health/incident
  detection was weakened — only a new constraint was added on top.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
These two rules were already the project's real practice — this prompt just makes them
self-enforcing instead of relying on a manual diagnostic each time an account connects or
a sender is chosen. The override escape hatch exists for real business judgment calls, but
every use of it is now visible and logged, not silent.