# V67.1 Phase 7.3 — Stage A Cohort Selection

## Method

Read-only evaluation of all 26 accounts. Masked IDs (`id8`). No phones in selection rationale.

## Rejected categories

| Category | Count (approx) | Reason |
|---|---|---|
| non-active status | 5 | deleted/suspended/pending/disconnected/green_api_deleted |
| open incident / BLOCKED_RESET | 1+ | safety |
| PAUSED mesh without inbound evidence preference | lower rank | weaker sensors |

## Selected

| Field | Value |
|---|---|
| Masked ID | `b12dbd81` |
| Status | `active` |
| Open incidents | 0 |
| Active suspension | none |
| Cooldown | none |
| Mesh | none |
| Inbound evidence | `received_today=209` (sensors readable) |
| Sent today | 0 |
| Expected seed state | conservative; not CAMPAIGN_READY/MATURE |

## Deterministic rule used

Among `active` + no open unresolved incidents + no active suspension + not BLOCKED_RESET: maximize `received_today`, then prefer stable clean sensors.

## No-send proof

Selection and enrollment do not call Green API send.
