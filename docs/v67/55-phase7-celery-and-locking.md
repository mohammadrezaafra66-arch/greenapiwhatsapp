# V67.1 Phase 7 — Celery and Locking

**Task:** `tasks.fleet_shadow_tick`  
**Beat:** `fleet-shadow-tick` every 300s (no-ops unless both flags true)

Flags default false and must stay false through Phase 7 implementation/tests.

**Lock:** `fleet:shadow:lock:{account_id}` via `ShadowAccountLock` (Redis SET NX + token release). Periodic fail-closed if Redis unavailable.

**Idempotency:** `{account_id}:{shadow_version}:{policy_version}:{slot}:{source}` unique.
