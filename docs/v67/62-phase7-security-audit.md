# V67.1 Phase 7.1 — Security Audit (Shadow-scoped temporary auth)

## Owner fact

No application-wide authentication system exists. Phase 7 introduced a temporary Shadow-scoped token.

## Findings

### P0 — Client role spoofing (FIXED in Phase 7.1)

**Before:** `X-Fleet-Shadow-Role` was accepted from the client if in `v67_shadow_allowed_roles`.
Any holder of the shared token could self-assign `admin` or `operator`.

**After:**
- Privilege role = `settings.v67_shadow_operator_role` only
- Client role header cannot elevate privilege
- Mismatched client role → **403** `shadow_role_spoof_rejected`
- Misconfigured role not in allowlist → **503**

### Token handling

| Check | Result |
|---|---|
| Unset token config → 503 | VERIFIED |
| Missing token → 401 | VERIFIED |
| Invalid token → 401 | VERIFIED |
| Valid token → backend role | VERIFIED |
| Token in API response | NOT present |
| Token logged | NOT present (only role + path) |
| Token in DB schema | NOT present |
| Token in frontend | N/A (no Shadow UI) |
| Constant-time compare | SHA-256 digests + compare_digest |

### Header spoofing

| Vector | Result |
|---|---|
| Client sets arbitrary role | Rejected if ≠ configured; ignored as privilege source |
| Bearer vs dedicated header | Both accepted for token only |
| Rate limit on run-once | Real in-process IP bucket (429) |

### Explicit non-claims

- This is **not** final application auth
- Shared static token is temporary internal credential
- Per-process rate limit is best-effort, not fleet-global WAF

## Verdict

**PASS** after P0 remediation. Temporary/scoped limitations documented honestly.
