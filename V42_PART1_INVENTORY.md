# V42 PART 1 — Inventory of hardcoded AI model references

Investigation only, no code change. Every place a specific model name is baked in, prioritized by
how much this pass cares about it. The vision path is the target; text-model hardcoding is recorded
but left alone per the prompt.

## The AI key pool / provider abstraction (the thing to extend, not replace)

- **`app/services/ai_key_pool.py`** — DB-backed pool of `AIKey` rows (`provider`, `api_key`,
  `status`, `success_count`, `fail_count`, `rate_limited_until`). `get_working_key(provider)` returns
  a random working, non-rate-limited key; `mark_success` / `mark_failure` update health. No model
  decision lives here — it only picks a *key*.
- **`app/services/gpt_service.py`** — the single source of truth for "which model to call". The
  `PROVIDERS` list maps each provider to one hardcoded `model` string; `PROVIDER_MODELS` /
  `PROVIDER_BASE` are derived from it and consumed by both the env-key path and the DB-pool path.
- The per-provider "which model" decision is made in exactly one way today: `PROVIDER_MODELS.get(
  provider, <fallback>)`. V42 replaces that lookup **for the vision path** with live discovery.

## Hardcoded model references

### Priority 1 — the vision path (what V42 must fix)

| # | Location | Reference | Role |
|---|----------|-----------|------|
| 1 | `services/gpt_service.py:20` | `"gemini": "gemini-2.0-flash"` | **The dead model.** Google discontinued it; 0/537 successes in the V40 diagnostic. Used by BOTH text and vision. |
| 2 | `services/gpt_service.py:18` | `"openai": "gpt-4o-mini"` | Vision-capable and currently valid, but still a hardcoded name that can be retired the same way. |
| 3 | `services/story_vision.py:127` | `model = PROVIDER_MODELS.get(key_obj.provider, key_obj.provider)` | **The actual vision call site.** Resolves gemini→`gemini-2.0-flash` (dead) and openai→`gpt-4o-mini`. This is the line PART 5 rewires. |
| 4 | `services/gpt_service.py:245` | `model = PROVIDER_MODELS.get(key_obj.provider, key_obj.provider)` | The TEXT pool path's model resolution (shares the same map). Out of scope for the fix, but shares the dead gemini entry — noted so PART 5 doesn't accidentally regress text. |

### Priority 2 — derived maps and fallbacks (change indirectly via #1/#2, or leave)

| # | Location | Reference | Role |
|---|----------|-----------|------|
| 5 | `services/gpt_service.py:25` | `PROVIDER_MODELS = {p["name"]: p["model"] ...}` | Derived from `PROVIDERS`; the map every call reads. |
| 6 | `services/gpt_service.py:26` | `PROVIDER_BASE = {p["name"]: p["base"] ...}` | Endpoint base per provider (not a model name; unaffected). |
| 7 | `services/gpt_service.py:210` | `PROVIDER_MODELS.get(provider, "gpt-4o-mini")` | Text `_call_provider` fallback default. Text scope — leave. |
| 8 | `services/gpt_service.py:185` | Gemini URL `.../models/{model}:generateContent` | Interpolates whatever model string it's given — will simply carry the discovered name once wired. |

### Priority 3 — text-only, explicitly out of scope this pass

| # | Location | Reference | Role |
|---|----------|-----------|------|
| 9 | `services/gpt_service.py:19` | `"deepseek": "deepseek-chat"` | Text-only provider; excluded from vision (`VISION_PROVIDERS = ["openai","gemini"]`). Not touched. |

### Non-code / cosmetic

| # | Location | Reference | Role |
|---|----------|-----------|------|
| 10 | `services/story_vision.py:5` | docstring: "openai (gpt-4o-mini) and gemini (gemini-2.0-flash)" | Comment only; update when the code changes so it doesn't mislead. |

## Vision provider set

`services/story_vision.py:25` — `VISION_PROVIDERS = ["openai", "gemini"]`. DeepSeek is text-only and
correctly excluded. V42's discovery applies to exactly these two, symmetrically.

## Conclusion / plan for PART 2–5

- The one call site that matters is `story_vision.py:127`. It resolves a model via the shared
  hardcoded `PROVIDER_MODELS` map, which still contains the dead `gemini-2.0-flash`.
- PART 2 adds `discover_available_models(provider, api_key)` calling each provider's live list-models
  API. PART 3 filters to vision-capable + picks a preferred (cheap-tier-first) model. PART 4 caches
  the pick per provider with TTL + re-discovers on repeated V40 vision failures. PART 5 replaces the
  `story_vision.py:127` lookup with that mechanism for both providers, behind the unchanged V40
  vision-failure guard. Text paths keep the existing map.
