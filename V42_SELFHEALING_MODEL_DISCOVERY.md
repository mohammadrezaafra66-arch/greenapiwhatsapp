# V42 MASTER PROMPT — Afrakala WhatsApp Sender
## Self-healing AI model selection: discover live, working vision models instead of hardcoding names

> MODE: FULLY AUTONOMOUS, RESUMABLE ACROSS SESSION LIMITS. Execute every PART end-to-end
> WITHOUT asking questions and WITHOUT waiting for approval. After each PART: run a heavy
> test suite and verify it works; only advance once every test passes. Commit and push
> each PART separately. If you hit a usage/session limit mid-part, stop cleanly; on the
> next invocation, run "git log --oneline -20" AND "git status" first, and resume from the
> next incomplete PART rather than restarting.
>
> OUTPUT LANGUAGE: report to the user in English only, per this project's CLAUDE.md rule.
> All in-app UI strings stay Persian/RTL as always.

---

## 0. CONTEXT (read first)

Project: C:\Users\AFRA\Desktop\bots\claudegreenapi
(GitHub: mohammadrezaafra66-arch/greenapiwhatsapp). Baseline: latest main, V17 through
V40 merged, plus the V40 media-type-bug fix and vision-failure guard (commit cf3ddfc).
V41 (mesh recovery for 7105325764) may be in progress separately — do not touch V41 work
in this pass, stay scoped to this prompt.

WHY THIS PROMPT EXISTS: the V40 story-image analysis pipeline calls a hardcoded model
name for Gemini ("gemini-2.0-flash") that was fully discontinued by Google, so every
single call failed silently (0 successes out of 537 attempts) — the code had no way to
notice the model no longer existed, it just kept retrying the same dead name forever.
Rather than just swapping in a new hardcoded name (which will eventually die too), build
a genuinely self-healing mechanism: for each configured AI provider, discover which
vision-capable models are ACTUALLY available right now by calling that provider's own
live "list models" API with the real configured key — do not guess or hardcode a model
name anywhere. Cache the discovered choice (to avoid calling "list models" on every
single request) but automatically re-discover if the cached model starts failing
repeatedly, so a future provider-side deprecation heals itself without a manual code fix.

### NON-NEGOTIABLE GUARDRAILS
1. NEVER enable Green API polling. Not relevant to this prompt's scope, but preserved.
2. Do NOT touch V41 (mesh recovery) files or work in progress.
3. Reuse the existing AI key pool / provider abstraction already used elsewhere in this
   project (OpenAI/DeepSeek/Gemini) — extend it, do not build a second, parallel one.
4. Do not weaken the V40 vision-failure guard (the fix that stops "AI call failed" and
   "AI saw nothing" from being recorded as the same outcome) — this prompt's model
   discovery sits BEHIND that guard, it does not replace it.
5. All UI strings Persian (Farsi), RTL. Code/vars/comments English.
6. Commit + push each PART separately ("V42 PART N: ...").

### WORKFLOW PER PART
Investigate the actual current AI key pool code and the hardcoded model references first
-> extend -> write/extend tests (mocking provider "list models" responses realistically,
based on each provider's actual current documented response shape) -> run the FULL
existing test suite -> verify zero regressions -> commit + push -> next PART.

---

## PART 1 — Investigate current hardcoded model usage

### 1.1 Investigate
- Find every place in the codebase that hardcodes a specific model name for AI calls,
  especially the vision path (currently "openai:gpt-4o-mini" and "gemini:gemini-2.0-flash"
  per the V40 diagnostic) — list them all, not just the vision ones, so PART 2-5's fix can
  be applied consistently wherever it matters most (prioritize vision first; text-model
  hardcoding can be left alone in this pass unless trivially covered by the same mechanism).
- Confirm the current AI key pool's structure: how keys/providers are configured, and
  where a per-provider "which model to call" decision is currently made.

### 1.2 Tests
No code change yet — just a report of every hardcoded model reference found, prioritized.
Commit + push "V42 PART 1: inventory of hardcoded model references".

---

## PART 2 — Live model discovery per provider

### 2.1 Build discover_available_models(provider, api_key)
- For OpenAI: call the real, live "list models" endpoint
  (GET https://api.openai.com/v1/models with the configured key) and parse the returned
  model id list.
- For Gemini: call the real, live "list models" endpoint for that provider (with the
  configured key) and parse the returned model list, including whatever capability/
  supported-methods metadata the response provides.
- These must be REAL HTTP calls against the actual provider using the actual configured
  key — not a hardcoded guess of what the response looks like. Handle auth failures
  (invalid/expired key) and network errors gracefully, returning a clear "could not
  discover models" result rather than crashing.

### 2.2 Tests
Mock each provider's list-models HTTP response using a realistic current shape (based on
what you can determine the real endpoints actually return, including relevant capability
fields for Gemini) and confirm the function correctly parses model ids and available
metadata; confirm an auth failure or network error returns a clear, non-crashing result.
Run full suite. Commit + push "V42 PART 2: live model discovery per provider".

---

## PART 3 — Determine vision-capability + pick a preferred model

### 3.1 Vision-capability filtering + preference order
- For Gemini: filter the discovered model list to ones that support image/multimodal
  input (using whatever capability signal the real API response provides — investigate
  this directly against the live response rather than assuming a specific field name).
- For OpenAI: since the plain model-list endpoint does not reliably expose a queryable
  "supports vision" flag, use a documented, maintainable rule (e.g., match against
  OpenAI's current known vision-capable model family patterns) — keep this rule isolated
  in one place so it's easy to update later without touching the discovery/caching logic.
- Preference order: prefer a smaller/cheaper tier (e.g., "mini"/"flash-lite"-class models)
  first for cost, falling back to any other vision-capable model actually available if the
  preferred tier isn't present.
- If NO vision-capable model is found for a given provider, return that clearly (so the
  caller can skip that provider entirely, exactly like the current dead-Gemini case,
  rather than crashing or silently misbehaving).

### 3.2 Tests
Given a realistic discovered model list, the correct preferred model is chosen; if the
preferred tier is absent but another vision-capable model exists, that one is chosen
instead; if none qualify, a clear "none available" result is returned.
Run full suite. Commit + push "V42 PART 3: vision-capability filtering + preference order".

---

## PART 4 — Cache the selection + automatic re-discovery on failure

### 4.1 Caching
- Cache the discovered/selected model per provider (with a timestamp) so normal vision
  calls do NOT hit the "list models" endpoint every single time — reuse the cached choice
  for a reasonable period (e.g., re-validate at most once every few hours, configurable).

### 4.2 Self-healing on failure
- If the currently cached model starts failing repeatedly (reuse the existing V40
  vision-failure signal — do not build a second failure-detection mechanism), trigger a
  fresh discovery + re-selection rather than continuing to retry a model that may have
  been deprecated. Log when this re-discovery happens and what changed (old model ->
  new model), so this is visible/auditable later.

### 4.3 Tests
A cached, working model is reused without re-calling "list models" on every request; a
model that starts failing repeatedly triggers a fresh discovery and switches to a
different valid model if one exists, or reports "no vision model currently available" if
none do; the re-discovery event is logged with old/new model names.
Run full suite. Commit + push "V42 PART 4: cache selection + automatic re-discovery on repeated failure".

---

## PART 5 — Wire into the existing vision-analysis call path

### 5.1 Replace hardcoded model names
- Update the story-image vision-analysis path (from V40) to use PART 2-4's discovery/
  cache/self-heal mechanism instead of the hardcoded "gpt-4o-mini" / "gemini-2.0-flash"
  constants — for BOTH providers, symmetrically, so whichever one(s) have a funded, valid
  key just work, without needing another manual code fix if a model name changes again.
- Preserve the existing V40 vision-failure guard's behavior exactly (a real failure to
  discover/call any model still correctly reports "vision unavailable," never a false
  "no product found").

### 5.2 Tests
The vision-analysis path, given a funded key pointing at a provider whose "list models"
call succeeds, uses the discovered model rather than any hardcoded name; given a provider
with no working vision model, it correctly reports unavailable (matching V40's existing
guard) rather than crashing or silently producing a wrong result.
Run full suite. Commit + push "V42 PART 5: wire discovery/self-heal into the vision-analysis path".

---

## PART 6 — Final wiring + full regression pass

### 6.1 Tests
Full end-to-end simulation: a provider whose previously-cached model has been
discontinued gets automatically re-discovered and switched to a currently-available
vision-capable model, with the switch logged; the story-analysis pipeline continues to
work correctly with the new model; a provider with no valid key or no vision-capable
model at all is skipped cleanly. Re-run the FULL pre-existing suite (V17-V40 plus the
V40 media-type/vision-guard fix) to confirm zero regressions.
Run full suite. Commit + push "V42 PART 6: final wiring + full regression pass".

---

## FINAL REPORT
- Test count before -> after, per-PART deltas, "zero regressions" confirmed.
- Exactly which model each configured provider (OpenAI, Gemini) actually resolved to
  right now, pulled live against the real configured keys.
- Confirm: no hardcoded vision model name remains in the story-analysis call path.
- Confirm: the V40 vision-failure guard's behavior is unchanged (a real outage still
  never produces a false "nothing found" result).
- Confirm: V41 work was not touched.
- The list of pushed commits, and the redeploy reminder:
  "docker compose build frontend && docker compose up -d frontend" and
  "docker compose up -d --force-recreate worker-general worker-webhooks beat backend".

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
This does not eliminate the possibility of a provider having zero working vision models
at some point (e.g., if a key's account has no billing at all) — it just ensures that
whichever models ARE actually usable right now get discovered and used automatically,
so a single vendor's model rename/retirement can never again silently break this feature
the way "gemini-2.0-flash" did.