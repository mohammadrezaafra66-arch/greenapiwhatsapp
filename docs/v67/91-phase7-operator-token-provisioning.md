# V67.1 Phase 7.3 — Operator Token Provisioning

## Status

**Provisioned** on ENV-A Backend via Compose `env_file` (`.env`).

## Properties verified

| Check | Result |
|---|---|
| Cryptographic generation | `secrets.token_urlsafe(48)` |
| Loaded in Backend | `token_set True`, length ≥ 32 |
| Role | Backend `operator` |
| Flags at provision time | both false (later enabled separately) |
| Git | `.env` gitignored; token not committed |
| Frontend | not present |
| Rotation | performed once after test assertion briefly echoed a live token fragment; new token loaded via container recreate |

## Token value

**REDACTED.** Never printed in this document.

## Auth behaviors

Covered by Phase 7.1 tests (503/401/403/success). Live token remains Backend-only.
