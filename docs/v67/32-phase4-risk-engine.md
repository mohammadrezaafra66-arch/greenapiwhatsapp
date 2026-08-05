# V67.1 Phase 4 — Risk Engine

**Module:** `app.services.risk_engine.RiskEngine`  
**Version:** `v67.4.risk.1`

## Levels

NORMAL → LOW → MEDIUM → HIGH → CRITICAL (from score thresholds 0/20/40/60/80).

## Factors

Open/history: blocked, suspended, forced_logout, device_restriction, yellowCard, auth_churn.  
Ops: breaker, webhook failures, queue backlog, duplicate sends, inactivity, traffic spike, repeated templates, device reuse, 30d counts.

## Output

`score`, `level`, `factors`, `explanations`. Never modifies runtime, campaigns, or send_gate.
