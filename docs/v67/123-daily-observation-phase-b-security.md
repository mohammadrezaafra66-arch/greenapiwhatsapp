# V67.1 — Phase B Security

- No `X-Fleet-Shadow-Token` in Frontend
- No LocalStorage/SessionStorage secrets for Shadow
- Delivery adapter returns sanitized contract only
- Bundle must not embed operator tokens
- Mutation HTTP methods not used by Observation page/API client
- Read-only behavioral expectation: no row changes in fleet/operational tables from GET
