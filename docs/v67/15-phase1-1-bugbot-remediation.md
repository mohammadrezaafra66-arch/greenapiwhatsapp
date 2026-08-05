# V67.1 Phase 1.1 — Bugbot Remediation

**Branch:** `feature/v67-autonomous-fleet-manager`  
**Mode:** Implementation (Bugbot fixes only)  
**Scope:** Fix exactly 3 Bugbot findings from Phase 1. No Phase 2 schema / AFM engines / real sends.

---

## Findings

| # | Severity | Location | Summary |
|---|---|---|---|
| 1 | HIGH | `campaign_runner.py` empty parallel fallback | Nested `run_campaign` while non-reentrant Redis lock held → completion never runs |
| 2 | MEDIUM | `campaigns.py` `start_campaign` | `selected_account_ids` forced parallel worker even when `parallel_accounts=false` |
| 3 | MEDIUM | `state_monitor.py` `apply_state` | Poll `suspended` fell through into generic danger cooldown/throttle |

---

## Root causes

1. **Lock reentrancy.** `run_campaign_parallel` acquires `CampaignLock`, then `_run_campaign_parallel_inner` delegated empty-account / empty-pending work to public `run_campaign`, which tries `SET NX` on the same key and exits without completing.
2. **Mode conflation.** Start routing used `parallel_accounts or selected_account_ids`, treating account-pool restriction as an execution-mode signal.
3. **Fallthrough.** After canonical `record_suspension`, `apply_state` continued into the blocked/logout kill-switch branch and invented `cooldown_until` / `throttle_until`, diverging from webhook + `record_suspension` (which deliberately omit cooldown).

---

## Exact fixes

### Finding 1 — single lock owner

- Empty `account_ids` and empty `pending` paths call `_run_campaign_inner` (lock already held).
- Public `run_campaign` is never nested from the parallel inner body.
- Outer `run_campaign_parallel` still acquires once and releases once in `finally`.

### Finding 2 — mode = `parallel_accounts` only

```text
parallel_accounts == true  → parallel worker (selected_account_ids narrows pool)
parallel_accounts == false → sequential worker (selected_account_ids enforced fail-closed)
```

Sequential start also pauses immediately when every selected account is unsafe (no unrestricted fallback).

### Finding 3 — canonical poll suspension

On `suspended`:

1. Set `account.status = suspended` (parity with webhook)
2. `refresh_suspended_until` (best-effort `getWaSettings`)
3. `record_suspension` (idempotent; fleet breaker inside)
4. `acted = suspended`
5. **return** — no generic cooldown/throttle fallthrough

---

## Files changed

| Path | Change |
|---|---|
| `backend/app/services/campaign_runner.py` | Parallel empty fallback → `_run_campaign_inner` |
| `backend/app/api/v1/campaigns.py` | Mode selection + sequential selected fail-closed |
| `backend/app/services/state_monitor.py` | Early return after canonical suspension |
| `backend/tests/test_v67_phase1_1_bugbot.py` | New Phase 1.1 regression suite |
| `backend/tests/test_v57_suspended_state.py` | Quarantine assertions match no-cooldown semantics |

---

## Tests added (names)

**Lock / fallback**

- `test_parallel_empty_pending_calls_inner_not_nested_run_campaign`
- `test_parallel_no_pending_fallback_completes_without_nested_lock`
- `test_parallel_fallback_exception_still_releases_lock`
- `test_parallel_inner_never_calls_public_run_campaign`

**Execution mode**

- `test_start_routing_uses_parallel_accounts_only`
- `test_execution_mode_matrix_parallel_flag_controls_worker` (cases 1–4)
- `test_selected_all_unsafe_pauses_sequential_without_unrestricted_fallback` (case 5)

**Suspension**

- `test_poll_suspended_calls_record_suspension_once_no_generic_cooldown`
- `test_poll_after_webhook_suspension_is_idempotent`
- `test_poll_stores_suspended_until_from_get_wa_settings`
- `test_poll_suspension_survives_get_wa_settings_failure`
- `test_apply_state_suspended_returns_before_generic_danger_branch`

---

## Suite results

| Scope | Result |
|---|---|
| Targeted Phase 1.1 + related | **139 passed, 0 failed** |
| Full Backend `pytest tests/` | **1696 passed, 0 failed** (2026-08-05) |
| Phase 1 baseline | 1684 passed |
| Net new tests | +12 |

No assertions weakened.

---

## Bugbot re-validation

| Finding | Status | Evidence |
|---|---|---|
| 1 | **RESOLVED** | `_run_campaign_parallel_inner` calls `_run_campaign_inner` only; source guard + lock acquire/release once tests |
| 2 | **RESOLVED** | `elif campaign.parallel_accounts:` + mode matrix tests 1–5 |
| 3 | **RESOLVED** | Early `return result` after `record_suspension`; poll tests prove no cooldown; source order guard |

---

## Remaining risks

- Parallel start with `parallel_accounts=true` and an empty eligible pool still schedules `task_run_campaign(id, [])`, which falls back to sequential under the same lock — pre-existing; not expanded in 1.1.
- Poll path still does not invent cooldown; send block relies on `status=suspended` + live_state + incident row (intentional, matches V65).
- No live Green API / real campaign execution exercised in this phase.

---

## Phase 2

**NOT started.** Wait for explicit: `Execute V67.1 Phase 2`
