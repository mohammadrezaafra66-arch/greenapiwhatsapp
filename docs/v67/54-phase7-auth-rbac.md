# V67.1 Phase 7 — Auth / RBAC (D-P7-16)

App has no global HTTP auth. Shadow routes use:

- Header `X-Fleet-Shadow-Token` or `Authorization: Bearer`
- Settings `v67_shadow_operator_token` (empty → **503** fail-closed)
- Header `X-Fleet-Shadow-Role` ∈ `v67_shadow_allowed_roles` (default `admin,operator`)
- Missing token → 401; wrong role → 403

Module: `app.services.shadow_auth.require_shadow_operator`  
Router: `app.api.v1.fleet_shadow`
