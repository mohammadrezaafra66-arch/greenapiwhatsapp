# V67.1 Phase 4 — Trust Engine

**Module:** `app.services.trust_engine.TrustEngine`  
**Version:** `v67.4.trust.1`  
**Mode:** Simulation / recommendation only

## Properties

- Deterministic for identical evidence + policy
- No AI / randomness
- Explains each component
- Missing evidence scores 0 and is listed
- `connected_at` alone never grants maturity (score capped ≤15)

## Evidence inputs

account_age_days, active_days, inbound/outbound diversity, bidirectional chats, response_ratio, delivery_success, webhook freshness, queue health, incident_free_days, device stability, native contacts, policy compliance.

## Output

`score` 0–100 + `components` + `explanations` + `missing` + `evidence_version`.

Does **not** mutate FleetState or send_gate.
