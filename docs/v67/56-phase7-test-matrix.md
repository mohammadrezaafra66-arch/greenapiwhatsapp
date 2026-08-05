# V67.1 Phase 7 — Test Matrix

| Area | File |
|---|---|
| Comparison classes / precedence | `test_v67_phase7_shadow_engine.py` |
| Flags default false / isolation | same |
| Auth 503/401/403 + role spoof | `test_v67_phase7_shadow_runtime.py` |
| Celery disabled no-op | same |
| Cutover refuse / dry-run no persist | same |
| Redis lock overlap / owner release | same |
| Idempotency key dimensions | same |
| Rate limit 429 | same |
| CLI invalid UUID | same |
| Migration up/down/re-up | same (container) |

Baseline before Phase 7: **1777 passed**.  
After Phase 7: **1797 passed, 0 failed**.  
After Phase 7.1: **1805 passed, 0 failed** (+8 auth/lock/idempotency/rate-limit/metrics coverage).
