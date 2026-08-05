# V67.1 Phase 1 — Runtime Safety Map

## Automated send paths → gate

| Path | Gate used | Fleet breaker | Notes |
|---|---|---|---|
| `campaign_runner._deliver_message` | `gate_check_automated` | yes (entry + gate) | Fail-closed |
| `campaign_runner.run_campaign` | CampaignLock + breaker | yes | No run if Redis down |
| `campaign_runner.run_campaign_parallel` | CampaignLock + breaker | yes | Same |
| `group_campaign_runner` | `gate_check_automated` | via gate | |
| `warmup_engine.execute_action` | flag + `gate_check_automated` | yes | Mesh autochat OFF by default |
| `warmup_helper_engine._send_from_main` | `gate_check_automated` (if db) | yes | TC KEEP |
| `warmup_cold_reply` | via `_send_from_main(..., db=)` | yes | |

## Sensors (unchanged sources)

| Sensor | Module |
|---|---|
| stateInstanceChanged | `webhook.handle_state_change` |
| getWaSettings / suspendedUntil | `state_monitor.refresh_suspended_until` |
| getStateInstance poll | `tasks.poll_instance_states` / send_gate cache |
| autoTyping preference | existing `set_warming_instance_settings` (not mutated in Phase 1) |

## Inbound preserved under breaker

Fleet breaker blocks **outbound automated sends** only. Webhook ingest, inbox write, and read-only APIs are not gated by the breaker module.

## Coexistence

```
Fleet 24h Suspend breaker  →  AFM/campaign/mesh/TC automated outbound
Mesh 48h killswitch        →  mesh enrollment pause (unchanged)
send_gate                  →  always final veto
```
