# V67.1 Phase 0 — Conflict Map

Contradictions between V67.1 assumptions and current code.  
**Hard Stop** = must resolve with owner before implementing the conflicting phase.  
**Soft** = adapter/mapping can reconcile without product-policy change.

---

## HARD STOP H1 — Artificial mesh interaction vs “no fake loops”

| V67.1 | Current |
|---|---|
| “Fake interaction, artificial message loops, fake behavior forbidden. Only real consented people.” | Mesh warm-up (`warmup_engine` + `warmup_ai`) sends AI-generated messages **between the operator’s own WhatsApp instances** to manufacture inbound/outbound flow. |

**Why hard:** Implementing JourneyOrchestrator *on top of* mesh without resolving this either (a) continues forbidden pattern or (b) disables the primary warm-up engine and breaks existing enrollments.

**Decision needed:** Retire mesh auto-chat in favor of human-participant + connected-warmer-only real chats; or amend V67.1 to allow own-account mesh as a transitional adapter under Shadow.

---

## HARD STOP H2 — Day 10 meaning

| V67.1 | Current |
|---|---|
| Day 10 = `WARMUP_READY` only; full campaign forbidden until graduation trial | General schedule: days 5–10 = `RAMPING` toward 100; days 11–24 = `MATURING`; day ≥25 = `GRADUATED`. Recovery: day ≥12 = `GRADUATED`. `Account.computed_daily_limit` still allows campaign sends with days_active formula (cap 5 for days &lt; 10). |

**Why hard:** “Graduation” and campaign eligibility are already wired to `GRADUATED` / days_active. Renaming day 10 without cutover rules will silently change who can send.

---

## HARD STOP H3 — Hard-coded 12→100 ramp vs Policy-only

| V67.1 | Current |
|---|---|
| `12 → 100` is suggested guidance; hard-code forbidden; live in Policy | `WarmupConfig.ramp_curve = [12, 20, 32, 48, 66, 84, 100]` shipped as defaults; scheduler indexes by day |

**Softening path:** Move curve into versioned Policy rows *without* deleting WarmupConfig until Shadow compare — but product must accept Policy as source of truth.

---

## HARD STOP H4 — Triple state space without single source of truth

Parallel enums today:

1. `AccountStatus` (`account.py`)
2. `WarmupState` (`warmup_state.py`)
3. Green API live state (`send_gate` / `InstanceLiveState`)
4. *(proposed)* V67 fleet states (~20 values)

Plus onboarding step integers and helper task statuses.

**Why hard:** Writing fleet transitions that ignore any of (1)–(3) will reopen V57/V65 bugs (suspended still “active”, warmth high, etc.).

**Required before Phase 4:** Explicit adapter matrix Account × Warmup × Live → Fleet (document + code), not a fourth write path.

---

## HARD STOP H5 — Schema migration strategy

| V67.1 | Current |
|---|---|
| Migrations with down scripts; idempotent unique | `create_all` + `main.py` `IF NOT EXISTS` DDL; `migrations/env.py` acknowledges no normal Alembic chain |

**Why hard:** Phase 2 acceptance (“up/down”) cannot pass on current tooling without introducing Alembic (or equivalent) carefully against a live DB that already has hand-patched columns.

---

## Conflict C1 — Circuit breaker windows (Soft/Hard borderline)

| V67.1 | Current |
|---|---|
| Stop if 2 distinct Suspend in 24h | Mesh breaker: 2 carded/blocked in **48h**, pauses whole mesh |
| Reset only owner + preflight | Killswitch auto-pauses; yellow-card auto-handles |

**Action:** Do not silently change 48→24 on mesh while adding fleet breaker; dual breakers can deadlock or double-pause.

---

## Conflict C2 — Peer ratio 1:3

| V67.1 | Current |
|---|---|
| Fixed 1:3 **not confirmed** | `peers_per_new_number_min=3`, `max=6`; V21 ratio cap tests |

Treat as Soft: make Policy-configurable; stop documenting 1:3 as fact.

---

## Conflict C3 — Campaign lock fail-open

| V67.1 | Current |
|---|---|
| Atomic claim + Redis lock; dual worker = one action | `run_campaign` proceeds **without lock if Redis errors** |

Hardening to fail-closed changes availability semantics — coordinate with ops before Phase 5.

---

## Conflict C4 — “Native contact” meaning

| V67.1 | Current |
|---|---|
| Contacts must be saved in the **phone’s primary address book** | Mesh handshake uses Green API `addContact` / flags `saved_as_contact_new/peer` |

API contact ≠ OS address book. Claiming “native verified” on current flags would be false compliance.

---

## Conflict C5 — Typing preference

| V67.1 | Current |
|---|---|
| Prefer `autoTyping` | Instance warming settings set `autoTyping:2`; campaigns use optional `typing_simulation` → SendTyping path |

Soft: unify policy; do not enable typing_simulation globally without canary.

---

## Conflict C6 — Maintenance / keep-warm idle

| V67.1 | Current |
|---|---|
| Few real daily messages; no official count | `keepwarm_max_idle_days=10`; safety scan erosion 14d / auto-logout 30d |

Soft: Policy knobs; avoid hard-coding new magic numbers.

---

## Conflict C7 — AI authority

| V67.1 | Current |
|---|---|
| AI suggests; Rule Engine decides | Send gates are rule-based (**aligned**); AI still chooses mesh/TC *content* and can drive volume via tick plans |

Soft but watch: ActionPlanner must not let AI raise caps.

---

## Conflict C8 — Recovery GRADUATED at ~day 12 vs WARMUP_READY

Recovery mode declares `GRADUATED` at day_index ≥ 12 after Green API’s ~10-day recovery narrative. V67 still requires trial before `CAMPAIGN_READY`.  
**Hard Stop** for recovery cutover messaging in UI (`فارغ‌التحصیلی` today implies campaign-ready).

---

## Conflict C9 — Branches / parallel work

`main` is 12 commits ahead of origin; redesign branch exists. Fleet work on `main` without a feature branch risks colliding with redesign and unpushed local commits.

**Soft process stop:** create `v67-phase*` branch before Phase 1 code (owner call).

---

## Contradicted assumptions checklist

| Assumption in V67.1 text | Contradicted by code? |
|---|---|
| No parallel send engine | False today — mesh + TC + campaign + group + status are parallel; AFM must orchestrate not duplicate |
| Day 10 only WARMUP_READY | Yes contradicted |
| 12→100 not hard-coded | Yes contradicted |
| 1:3 ratio unconfirmed | Code still centers ~3 peers |
| stateInstanceChanged primary | Largely true (plus 60s poll backup) |
| getWaSettings for suspendedUntil | True (V57) |
| Incident → REWARM_REQUIRED | Only partial (mesh BLOCKED_RESET / recovery reset); fleet enum absent |
| Token never frontend | Appears held (keep) |
| Webhook-only receive | True for messages; health GETs allowed |

---

## Recommended owner decisions before Phase 1

1. Mesh AI own-account chat: **retire / shadow-only / amend V67**?  
2. Day-10 and graduation vocabulary in Persian UI — freeze glossary.  
3. Introduce Alembic now or defer down-scripts to Phase 2 with explicit waiver?  
4. Fail-open vs fail-closed Redis locks.  
5. Fleet breaker window 24h vs existing mesh 48h coexistence.
