# V67.1 Phase 7.2 — Temporary Shadow Operator Auth Preflight

**Scope:** Temporary Shadow-scoped credential only. Not application-wide auth.

## Required configuration (future provisioning — not performed)

| Variable | Requirement |
|---|---|
| `V67_SHADOW_OPERATOR_TOKEN` | Strong random secret; Backend-only; empty → API **503** |
| `V67_SHADOW_OPERATOR_ROLE` | Backend-controlled (default `operator`); must be in allowlist |
| `V67_SHADOW_ALLOWED_ROLES` | Server allowlist for configured role |

## Current ENV-A state

- Token: **unset** (empty) → Shadow APIs fail-closed with 503 — verified
- Role default: `operator`
- Client role header cannot grant privilege (Phase 7.1 fix)

## Token generation procedure (offline; do not run for production in 7.2)

```bash
# Example strong token (store only in Backend env / secret manager)
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Secure storage

- Set only in Backend/worker/Beat environment (Compose `env_file` or secret store)
- Never commit to Git
- Never place in frontend env / LocalStorage / SessionStorage
- Never return in API JSON
- Never write into `fleet_shadow_snapshots`

## Rotation

1. Generate new token
2. Update Backend env
3. Restart Backend (and any process loading settings once)
4. Invalidate old token by removal
5. Audit log entries show role/path only (no token)

## Emergency revocation

1. Clear `V67_SHADOW_OPERATOR_TOKEN` (set empty)
2. Restart API → routes return **503**
3. Optionally set both Shadow feature flags false (when they were ever true)

## Who may possess it

Owner-designated operators only (see D-SE-10). Single shared temporary credential — document holders.

## Access audit

- Successful auth logs: `shadow_operator_auth_ok role=<role> path=<path>` (no token)
- Failures: HTTP 401/403/503 without token echo

## Explicit limitation

This mechanism is temporary and Shadow-scoped. It must not become silent final application authentication.
