# V67.1 Phase 7 — Comparison Engine

**Module:** `app.services.shadow_comparison.ShadowComparisonEngine`  
**Version:** `v67.7.shadow.1`

Pure deterministic. Precedence: RUNTIME_UNKNOWN → SENSOR_STALE → major incident → breaker → blocked FleetState → journey fail-closed / high-volume readiness → policy mismatch → insufficient evidence → LEGACY_MORE_PERMISSIVE → V67_MORE_PERMISSIVE → SAFE_MISMATCH → MATCH.

Dangerous threshold status always `UNRATIFIED` (D-P7-11).
