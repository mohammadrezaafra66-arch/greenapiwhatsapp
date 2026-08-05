# V67.1 Phase 7.1 — Test Quality Audit

## Method

Reviewed Phase 7 tests for tautology, source-string-only isolation as sole proof, missing auth paths, and weak mocks.

## Files

| File | Role |
|---|---|
| `backend/tests/test_v67_phase7_shadow_engine.py` | Comparison + freshness + flag defaults + source isolation |
| `backend/tests/test_v67_phase7_shadow_runtime.py` | Auth, Celery no-op, cutover, dry-run, lock, idempotency, rate limit |

## Weaknesses found (pre-7.1)

| Weakness | Severity | Remediation |
|---|---|---|
| Auth tested token paths but trusted client role | P0 | Fixed: backend-derived role + spoof 403 test |
| No concurrency lock ownership test | P1 | Added `test_shadow_lock_owner_only_and_no_overlap` |
| Idempotency dimensions only implied | P2 | Added `test_idempotency_key_dimensions` |
| Rate limit registration-only risk | P2 | Added `test_rate_limit_enforced` (behavioral 429) |
| Isolation partly source-string | P2 | Kept source checks; added dry-run `db.add` not called + cutover refusal |
| Migration CHECK not hit in CI without container | Acceptable | Roundtrip marked `skipif` container; CHECK insert attempted when available |
| `test_safe_mismatch_graduated` allows multiple classes | P3 | Soft; still asserts non-crash deterministic path |

## Remaining limitations (honest)

- Full DB no-mutation across all operational tables requires integration DB; dry-run asserts `db.add` not called.
- Forbidden-call graph uses source inspection + send_gate untouched; behavioral mocks cover scoring/preview only.
- Migration constraint tests run in container (`/app/alembic.ini`).

## Verdict on test credibility

After Phase 7.1 strengthening: **CREDIBLE for audit gate**, with documented integration gaps above.
Do not treat source-string checks alone as sole isolation proof; they are supporting evidence.
