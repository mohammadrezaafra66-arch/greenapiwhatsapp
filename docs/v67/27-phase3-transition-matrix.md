# V67.1 Phase 3 — Transition Matrix (engine)

Pure function: `evaluate_transition(...)` in `journey_transition.py`.

## Precedence

1. RETIRED / FAILED  
2. BLOCKED  
3. FORCED_LOGOUT / device_restriction  
4. SUSPENDED  
5. Fleet breaker → PAUSED  
6. Critical incident (yellowCard/auth_churn) → AT_RISK  
7. Explicit PAUSED  
8. Policy fail-closed  
9. Normal ladder (NEW_ACCOUNT)

## Normal ladder (stops at WARMUP_READY)

NEW → PRECHECK → QR_WAITING → READY_TO_LINK → AUTHORIZED_QUIET → INBOUND_BUILDING → BIDIRECTIONAL_BUILDING → CONTROLLED_RAMP → **WARMUP_READY**

No automatic GRADUATION_TRIAL / CAMPAIGN_READY / MATURE.

## Rewarm

REWARM_REQUIRED → PRECHECK (or AUTHORIZED_QUIET if live authorized)

## Evidence

Reuses activity_evidence where available; connected_at alone never graduates; total_flow = inbound + outbound from policy `incoming_plus_outgoing`.
