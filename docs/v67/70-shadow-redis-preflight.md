# V67.1 Phase 7.2 — Shadow Redis Preflight

## ENV-A checks (disposable key only)

| Check | Result |
|---|---|
| Reachable from Backend | Yes (`get_redis` via Backend container) |
| Auth | No Redis password configured in Compose (URL `redis://redis:6379/0`) |
| DB index | `0` |
| PING | `PONG` |
| Keyspace size | ~17066 keys (pre-existing operational keys) |
| Eviction policy | `noeviction` |
| maxmemory | `0` (unlimited) |
| NX SET | Pass (`set_nx True`, ~9.55 ms) |
| Lua owner-only release | Pass (owner `1`, wrong-owner `0`, key remained) |
| Disposable cleanup | Pass (`v67:preflight:shadow:<uuid>` deleted) |
| Live Shadow locks present | None observed for `fleet:shadow:lock:*` scan sample |
| ShadowAccountLock acquire/release | Pass on disposable account UUID |

## Fail-closed

Shadow lock sets `fail_closed_reason=redis_unavailable` on Redis errors (code path verified in Phase 7.1 tests).

## Collision risk

Shadow locks use `fleet:shadow:lock:{account_id}`. Preflight used only `v67:preflight:shadow:*`. No FLUSH performed.

## Verdict

**Redis technically ready for future Shadow locks on ENV-A.**  
Enablement still requires owner authorization (flags remain false).
