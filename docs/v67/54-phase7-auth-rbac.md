# V67.1 Phase 7 — Auth / RBAC (D-P7-16) — Temporary Shadow-scoped control

**Scope:** This is NOT application-wide authentication. There is currently no global HTTP auth system.
Phase 7 uses a **temporary, Shadow-scoped operator credential** for `/api/v1/fleet/shadow/*` only.

## Mechanism (Phase 7.1 remediated)

| Control | Behavior |
|---|---|
| `v67_shadow_operator_token` | Backend setting only. Empty → **503** fail-closed |
| `X-Fleet-Shadow-Token` or `Authorization: Bearer` | Required; missing/invalid → **401** |
| `v67_shadow_operator_role` | Backend-configured role (default `operator`) |
| `v67_shadow_allowed_roles` | Server-side allowlist validating configured role |
| `X-Fleet-Shadow-Role` | **Not trusted for privilege.** If supplied and ≠ configured role → **403** spoof reject |

Module: `app.services.shadow_auth.require_shadow_operator`  
Router: `app.api.v1.fleet_shadow`

## Security properties

- Token compared via SHA-256 digests + `hmac.compare_digest` (length-safe)
- Role is **never** client-assigned
- Token never returned in API responses
- Token never logged
- Token never stored in `fleet_shadow_snapshots`
- Token not shipped to frontend (no Shadow UI)

## Rotation / ops

1. Set a strong secret in Backend env: `V67_SHADOW_OPERATOR_TOKEN`
2. Optionally set `V67_SHADOW_OPERATOR_ROLE=operator` (must be in allowlist)
3. Rotate by changing Backend env and restarting API workers
4. Do not treat this as final product auth architecture

## Explicit limitation

A single static shared token is acceptable only as a temporary internal operator control for Phase 7 observational APIs.
A future application-wide auth/session system must replace this before production multi-user use.
