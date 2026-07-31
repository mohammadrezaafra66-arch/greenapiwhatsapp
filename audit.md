# Deep Audit — Prompts vs. Delivered Code

- Repository: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
- HEAD: `5f7d944 V51 PART 1: auto-analyze story backlog after each scheduled fetch`
- Generated: 2026-07-31 07:00:28 UTC by `deep_audit.py`
- Prompts analyzed: **55**

> Prompt bodies are treated as confidential. This report contains only titles, one-line goals, PART headings and counts — never prompt content.

## Reading this report — a required caveat

Prompt→commit linking relies on the `V<n> PART <k>: ...` commit-subject convention, which this project only adopted at **V16**. Every prompt numbered below V16 is therefore marked **UNVERIFIABLE**, not 'not done' — the early work was committed under free-form subjects (`v2.0`, `feat: ...`) and cannot be matched by tag. For those, code markers are the only available evidence.

---

# ساخته‌شده‌ها / Built

## V16_MASTER_PROMPT.md — V16
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V16_MASTER_PROMPT.md`
- Goal: 0. CONTEXT (read first, do not skip)
- Commits: 6
  - `455cc5a` V16 PART 6: ngrok Windows-service setup (config + admin instructions)
  - `96de952` V16 PART 5: smart warm-up (phrases, timing, dashboard, batch)
  - `469e522` V16 PART 4: verify/ensure live per-message pricing
  - `c836c9d` V16 PART 3: advertising links (CRUD + weighted append in campaigns)
  - `e0eb088` V16 PART 2: catalog browse (brand dropdown + full table) — and fix the "۰ محصول" root cause
  - `239c51c` V16 PART 1: Supabase diagnostics + graceful degradation
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\NGROK_SERVICE_SETUP.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\adlinks.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\campaigns.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reporting.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\config.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\__init__.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\advertising.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\campaign.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\adlinks.py`
- Tests: 5 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v16_part1.py`

## V17_AUTO_WARMUP_MESH_PROMPT.md — V17
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V17_AUTO_WARMUP_MESH_PROMPT.md`
- Goal: Automatic, AI-driven, mesh-based warm-up + typing simulation
- Commits: 6
  - `7d3d4b2` V17 PART 6: warm-up dashboard (Persian RTL)
  - `fb48304` V17 PART 5: kill-switch + chain-ban breaker + reset detection
  - `287f30e` V17 PART 4: automatic jittered AI mesh scheduler
  - `66a0c3e` V17 PART 3: enrollment + pre-flight + mutual-contact mesh handshake
  - `6504c27` V17 PART 2: warm-up state machine + mesh schema
  - `755dd8e` V17 PART 1: typing simulation (typingTime/SendTyping)
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\campaigns.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\webhook.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\__init__.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\account.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\campaign.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_mesh.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\campaign_runner.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\green_api.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\typing_sim.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_content.py`
- Tests: 6 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v17_part1.py`

## V18_FIX_FANOUT_AND_WARMUP_WIRING.md — V18
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V18_FIX_FANOUT_AND_WARMUP_WIRING.md`
- Goal: Fix silent multi-account fan-out + wire the "smart warm-up" toggle to the V17 mesh
- Commits: 2
  - `4a6528a` V18 PART 2: wire smart-warmup toggle to V17 mesh + enrollment-based campaign exclusion
  - `e9df960` V18 PART 1: fail-closed account selection (no silent fan-out)
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\accounts.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\campaigns.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\account_selection.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\campaign_runner.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\group_campaign_runner.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_auto.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_exclusion.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\Accounts.jsx`
- Tests: 2 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v18_part1.py`

## V19_GROUP_WARMUP_PROMPT.md — V19
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V19_GROUP_WARMUP_PROMPT.md`
- Goal: Group-based warm-up: add cold numbers to admin-owned groups (ADD to the mesh, don't replace it)
- Commits: 5
  - `d1d83a7` V19 PART 5: dashboard group placements + one-toggle wiring
  - `64bc712` V19 PART 4: automatic group-placement scheduler (fixed anti-ban schedule)
  - `f443c69` V19 PART 3: group warm-up UI + manual link vault
  - `11d3737` V19 PART 2: group warm-up schema + link vault
  - `7abbdb1` V19 PART 1: read warm account admin groups
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\__init__.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_mesh.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\green_api.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_dashboard.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_group_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_group_scheduler.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_groups.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\workers\celery_app.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\workers\tasks.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\api.js`
- Tests: 5 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v19_part1.py`

## V20_FIX_TOGGLE_AND_WARM_PEERS.md — V20
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V20_FIX_TOGGLE_AND_WARM_PEERS.md`
- Goal: Fix stuck warm-up toggle + make existing warm accounts usable as mesh PEERS
- Commits: 3
  - `c99bcff` V20 PART 3: dashboard roles + no-peer notice
  - `04662ea` V20 PART 2: warm-peer designation (sender role separate from being warmed)
  - `1aca0eb` V20 PART 1: fix stuck warm-up toggle (persist disable + enrollment-based checkbox + clear stale flags)
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\accounts.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_dashboard.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_exclusion.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_mesh_service.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\Accounts.jsx`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\Warmup.jsx`
- Tests: 3 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v20_part1.py`

## V21_RATIO_AND_BREAKER.md — V21
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V21_RATIO_AND_BREAKER.md`
- Goal: Enforce warm:cold ratio, exclude unconnected accounts, smarter chain-ban breaker
- Commits: 5
  - `c9b74a8` V21 PART 4: dashboard ratio + capacity + breaker visibility
  - `e6fa4ec` V21 PART 3: breaker counts distinct numbers, not incidents
  - `54e2773` V21 PART 2: exclude pending/unconnected numbers from mesh
  - `2e5231e` V21 PART 1: enforce 1:2 warm-to-cold ratio cap
  - `6f9f564` V21: fix mesh handshake blocker (null phone + addContact schema)
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\green_api.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_dashboard.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_killswitch.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_mesh_service.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts_heal_stuck_edges.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts_run_backfill_phones.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\Warmup.jsx`
- Tests: 8 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v17_part3.py`

## V27_ANTIBAN_HARDENING.md — V27
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V27_ANTIBAN_HARDENING.md`
- Goal: Anti-ban hardening: peer-health gating, peer-level rate limits, minimum peer age, and 7 additional safeguards
- Commits: 10
  - `4be89dc` V27 PART 10: tariff/quota (466) monitoring and alerting
  - `296736b` V27 PART 9: minimum-2-peers requirement + staggered cold-number starts
  - `b405914` V27 PART 8: live quality-score auto-throttle
  - `d9016b7` V27 PART 7: volume-spike guard for all sending instances
  - `4196755` V27 PART 6: media-fingerprint reuse tracking for campaigns
  - `3867d66` V27 PART 5: lazy cached number-existence validation
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\accounts.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\campaigns.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\webhook.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\__init__.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\instance_state.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\media_send.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\number_check.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\campaign_runner.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\green_api.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\group_campaign_runner.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\media_fingerprint.py`
- Tests: 10 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v27_part1.py`

## V28_FLEXIBLE_OUTREACH_ASSISTANT.md — V28
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V28_FLEXIBLE_OUTREACH_ASSISTANT.md`
- Goal: Flexible multi-sender AI-personalized outreach assistant (generalizes V25's fixed-25 helper system)
- Commits: 5
  - `dcc0d67` V28 PART 5: outreach dashboard
  - `179595d` V28 PART 4: hard pacing + health gate for outreach sending
  - `83008c3` V28 PART 3: AI-personalized per-contact messages from a one-line brief
  - `95230f5` V28 PART 2: sender selection + per-sender contact-list API
  - `5e685ee` V28 PART 1: generalize helper schema (multi-sender, mandatory name, no hard cap)
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\__init__.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\outreach_message.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_helper_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_helper_service.py`
- Tests: 6 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v25_part1.py`

## V29_TEAM_COLLABORATION_REVISED.md — V29
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V29_TEAM_COLLABORATION_REVISED.md`
- Goal: «همکاری تیمی» (Team Collaboration): full personnel-outreach warm-up system
- Commits: 11
  - `e020f50` V29 PART 10: final wiring + dashboard integration + cross-guardrail verification
  - `344b3c9` V29 PART 9: dedicated Team Collaboration log (Shamsi dates)
  - `ea8f6a4` V29 PART 8 fix: serve warmth via dedicated /warmth endpoint (keep senders list shape stable)
  - `9d7ced1` V29 PART 8: sender warmth score/analysis
  - `3fa19f1` V29 PART 7: per-cold-account enrollment + 10-day automatic cycle
  - `c581442` V29 PART 6: confirm single reminder works with thread-aware flow
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\New Microsoft Visio Drawing.vsdx`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\New Text Document (2).txt`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V13_MASTER_PROMPT.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V14_MASTER_PROMPT.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V15_BUGFIX_UX_PROMPT.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V16_MASTER_PROMPT.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V17_AUTO_WARMUP_MESH_PROMPT.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V18_FIX_FANOUT_AND_WARMUP_WIRING.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V19_GROUP_WARMUP_PROMPT.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V20_FIX_TOGGLE_AND_WARM_PEERS.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V21_RATIO_AND_BREAKER.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V22_QR_ANTIBAN_RULES.md`
- Tests: 10 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v29_part1.py`

## V30_TEAM_COLLAB_REFINEMENTS.md — V30
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V30_TEAM_COLLAB_REFINEMENTS.md`
- Goal: Complete «همکاری تیمی» frontend + 10 refinements (pacing, variety, work-hours, escalation, typing, counters, dashboard bug)
- Commits: 9
  - `2ce11e3` V30 PART 9: final wiring + full regression pass
  - `67ab8e3` V30 PART 8: fix "today's sent count" dashboard bug
  - `5c33dac` V30 PART 7: running request-count display in the log
  - `3de7ab2` V30 PART 6: variable typing-time + genuinely random jitter + compliance pass
  - `e512f91` V30 PART 5: varied AI content (emoji, tone) + staggered thank-yous
  - `8e60047` V30 PART 4: completion-based escalation to 2 new cold accounts
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V30_TEAM_COLLAB_REFINEMENTS.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\dashboard.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\outreach_message.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\peer_pacer.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\send_metrics.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_ask_spacing.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_cold_reply.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_content.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_helper_engine.py`
- Tests: 8 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v30_part1.py`

## V33_STALL_FIX_AND_REMINDER_CAP.md — V33
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V33_STALL_FIX_AND_REMINDER_CAP.md`
- Goal: Fix the pending-stall root cause, enforce the 2-cold-account ceiling, clean orphaned tasks, and cap reminders at exactly 2 (then stop)
- Commits: 5
  - `0d2678d` V33 PART 5: final wiring + full regression pass
  - `1d29bbb` V33 PART 4: cap reminders at exactly 2, then stop (terminal no_response)
  - `bc868d4` V33 PART 3: clean up orphaned tasks + prevent recurrence
  - `c1b32a2` V33 PART 2: enforce 2-cold-account ceiling + reconcile existing violations
  - `c6d6b08` V33 PART 1: fix root cause of tasks stuck pending
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V33_STALL_FIX_AND_REMINDER_CAP.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_helper_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_helper_service.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_team_schedule.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\conftest.py`
- Tests: 10 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v25_part1.py`

## V39_UNIVERSAL_COOLDOWN_AND_ELIGIBILITY_GATE.md — V39
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V39_UNIVERSAL_COOLDOWN_AND_ELIGIBILITY_GATE.md`
- Goal: Two permanent, system-enforced rules: universal connect-cooldown + hard sender-eligibility gate (with logged override)
- Commits: 5
  - `26cbf98` V39 PART 5: final wiring + full regression pass
  - `b840837` V39 PART 4: frontend warning/confirmation UI for sender-eligibility override
  - `a0c7eec` V39 PART 3: send-time defense-in-depth for sender eligibility
  - `4b14021` V39 PART 2: hard sender-eligibility gate with logged override
  - `60095a9` V39 PART 1: universal 24h connect-cooldown across all send paths
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\accounts.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\partner.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\webhook.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\account.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\send_gate.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\sender_eligibility.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_helper_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_helper_log.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_reconnect_rest.py`
- Tests: 7 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v28_part2.py`

## V40_STORY_PRODUCT_ANALYSIS.md — V40
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V40_STORY_PRODUCT_ANALYSIS.md`
- Goal: Story product analysis: new tab inside Stories, AI text/image detection, feeds the existing product report, per-contact trend, catalog-spotted alert
- Commits: 11
  - `cf3ddfc` V40 FIX: never cache a failed-vision result; purge rows an AI outage poisoned
  - `965d31e` V40 FIX: correct Green API story media-type detection + free mis-analyzed stories
  - `4e4b2cb` V40 PART 8: final wiring + full regression pass
  - `3a6fee0` V40 PART 7: catalog-product-spotted alert (price-free version)
  - `eafcac9` V40 PART 6: per-contact advertising trend over time
  - `c805bd1` V40 PART 5: story-detected products feed the existing report with source tagging
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\.gitignore`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reporting.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reports_public.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\statuses.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\webhook.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\__init__.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\catalog_alert.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\received_status.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\reporting.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\story_analysis.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\catalog_spot_alert.py`
- Tests: 12 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_reports_public.py`

## V41_PATH_B_AUTOMATED_WAIT.md — V41
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V41_PATH_B_AUTOMATED_WAIT.md`
- Goal: Do not relax any rule; automatically apply the recovery enrollment for 7105325764 the moment both real conditions clear naturally
- Commits: 8
  - `0c3f6cb` V41 Path B PART 3: final wiring + full regression pass
  - `d4adaec` V41 Path B PART 2: dashboard visibility for the pending auto-apply state
  - `fcab378` V41 Path B PART 1: scheduled automatic recheck + auto-apply when both conditions naturally clear
  - `3de72a2` V41 PART 5: dashboard visibility + final wiring
  - `5471e0e` V41 PART 4: add halted recovery enrollment preflight
  - `6c96d5f` V41 PART 3: confirm/indicate TC sender pause during mesh recovery
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\webhook.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_mesh.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\sender_eligibility.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_dashboard.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_killswitch.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_recovery_autoenroll.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_recovery_enroll.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_scheduler.py`
- Tests: 8 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v41_part1.py`

## V41_RECOVERY_REWARM.md — V41
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V41_RECOVERY_REWARM.md`
- Goal: Recovery re-warm of 7105325764 via the existing mesh engine, per Green API's exact 10-day guidance
- Commits: 8
  - `0c3f6cb` V41 Path B PART 3: final wiring + full regression pass
  - `d4adaec` V41 Path B PART 2: dashboard visibility for the pending auto-apply state
  - `fcab378` V41 Path B PART 1: scheduled automatic recheck + auto-apply when both conditions naturally clear
  - `3de72a2` V41 PART 5: dashboard visibility + final wiring
  - `5471e0e` V41 PART 4: add halted recovery enrollment preflight
  - `6c96d5f` V41 PART 3: confirm/indicate TC sender pause during mesh recovery
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup_helpers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\webhook.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\warmup_mesh.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\sender_eligibility.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_dashboard.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_engine.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_killswitch.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_recovery_autoenroll.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_recovery_enroll.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_scheduler.py`
- Tests: 8 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v41_part1.py`

## V42_PART1_INVENTORY.md — V42
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V42_PART1_INVENTORY.md`
- Goal: The AI key pool / provider abstraction (the thing to extend, not replace)
- Commits: 6
  - `aa99013` V42 PART 6: final wiring + full regression pass
  - `9a98aa0` V42 PART 5: wire discovery/self-heal into the vision-analysis path
  - `78347ac` V42 PART 4: cache selection + automatic re-discovery on repeated failure
  - `1222e5a` V42 PART 3: vision-capability filtering + preference order
  - `52f8d40` V42 PART 2: live model discovery per provider
  - `9cd71d5` V42 PART 1: inventory of hardcoded model references
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V42_PART1_INVENTORY.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\ai_model_discovery.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\ai_vision_model_cache.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\ai_vision_select.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\story_vision.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\conftest.py`
- Tests: 5 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v42_part2_discovery.py`

## V42_SELFHEALING_MODEL_DISCOVERY.md — V42
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V42_SELFHEALING_MODEL_DISCOVERY.md`
- Goal: Self-healing AI model selection: discover live, working vision models instead of hardcoding names
- Commits: 6
  - `aa99013` V42 PART 6: final wiring + full regression pass
  - `9a98aa0` V42 PART 5: wire discovery/self-heal into the vision-analysis path
  - `78347ac` V42 PART 4: cache selection + automatic re-discovery on repeated failure
  - `1222e5a` V42 PART 3: vision-capability filtering + preference order
  - `52f8d40` V42 PART 2: live model discovery per provider
  - `9cd71d5` V42 PART 1: inventory of hardcoded model references
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V42_PART1_INVENTORY.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\ai_model_discovery.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\ai_vision_model_cache.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\ai_vision_select.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\story_vision.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\conftest.py`
- Tests: 5 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v42_part2_discovery.py`

## V43_REPORTING_FILTER_EXPANSION.md — V43
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V43_REPORTING_FILTER_EXPANSION.md`
- Goal: Expand the reporting page's date-range and product-count filters
- Commits: 4
  - `c383e9a` V43 FIX: align public reports top-products ceiling with the UI (500 -> 1000)
  - `6230498` V43 PART 3: final wiring + full regression pass
  - `f170f10` V43 PART 2: expand the reporting product-count limit up to 1000
  - `527310b` V43 PART 1: expand the reporting date-range options
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reports_public.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\product_reports.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\Reporting.jsx`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\reporting.js`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\reporting.test.js`
- Tests: 4 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_reports_public.py`

## V44_MERGE_VERIFY_AND_SEARCH.md — V44
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V44_MERGE_VERIFY_AND_SEARCH.md`
- Goal: Verify/fix product-name merging in the top-products report + add search
- Commits: 4
  - `ea2d136` V44 PART 4: final wiring + full regression pass
  - `e40b5cd` V44 PART 3: add search to the top-products report table
  - `d8ef883` V44 PART 2: fix product-name grouping for near-duplicate mentions
  - `6f93b95` V44 PART 1: investigate current product-name grouping behavior (findings only)
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reporting.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\product_match.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\product_reports.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\api.js`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\Reporting.jsx`
- Tests: 5 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v43_part3_e2e.py`

## V45_EXCLUSION_AND_ACTIVE_CONTACTS.md — V45
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V45_EXCLUSION_AND_ACTIVE_CONTACTS.md`
- Goal: Exclude our own numbers from product detection + harvest an active-contacts list
- Commits: 4
  - `6288f8d` V45 PART 4: final wiring + full regression pass
  - `873bb1d` V45 PART 3: active WhatsApp contacts harvesting list
  - `64da2e1` V45 PART 2: wire own-number exclusion before any AI call, all sources
  - `1c6b977` V45 PART 1: own-number exclusion list + management UI
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\active_contacts.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\own_numbers.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reporting.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reports_public.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\statuses.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\webhook.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\main.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\__init__.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\active_contact.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\models\own_number.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\active_contact_harvest.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\own_number_exclusion.py`
- Tests: 4 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v45_part1.py`

## V48_PART1_INVENTORY.md — V48
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V48_PART1_INVENTORY.md`
- Goal: 1. `/accounts` (Accounts.jsx)
- Commits: 4
  - `4bc1071` V48 PART 4: final wiring + full regression pass
  - `d67a388` V48 PART 3: build the unified all-accounts overview page
  - `925ee72` V48 PART 2: build the all-accounts aggregation endpoint
  - `fe9119a` V48 PART 1: inventory the four existing account-data sources
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V48_PART1_INVENTORY.md`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\accounts.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\incidents.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\warmup.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\account_health.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\accounts_overview.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_exclusion.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\App.jsx`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\api.js`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\components\Layout.jsx`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\nav\inventory.test.js`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\nav\reorg.test.js`
- Tests: 2 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v48_part2.py`

## V49_RETENTION_AND_DETECTION_FIX.md — V49
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V49_RETENTION_AND_DETECTION_FIX.md`
- Goal: Fix the 2-day data purge + reconcile date-range UI + close a detection gap
- Commits: 4
  - `eb52572` V49 PART 4: end-to-end regression across retention + date-range + detection
  - `51a5c73` V49 PART 3: close detection gap for capacity+brand-style product listings
  - `b393d75` V49 PART 2: reconcile date-range UI options with the real 90-day retention ceiling
  - `be4f27f` V49 PART 1: extend data retention from 2 days to 90 days
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reporting.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\reports_public.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\product_match.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\product_reports.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\workers\tasks.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\Reporting.jsx`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\reporting.js`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\pages\reporting.test.js`
- Tests: 7 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_product_match.py`

## V50_STORY_FETCH_RESILIENCE.md — V50
- Prompt: `C:\Users\AFRA\Desktop\bots\claudegreenapi\V50_STORY_FETCH_RESILIENCE.md`
- Goal: Scheduled auto-fetch for stories + multi-account resilience
- Commits: 3
  - `0326a55` V50 PART 3: end-to-end simulation of scheduled multi-account story fetch
  - `d1a988f` V50 PART 2: scheduled automatic story fetch (Celery beat)
  - `964dddc` V50 PART 1: multi-account story fetch (loop over eligible accounts)
- Output files:
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\story_fetch.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\workers\celery_app.py`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\workers\tasks.py`
- Tests: 3 file(s), e.g. `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v50_part1.py`

---

# نیمه‌کاره‌ها / Half-done

## Prompts with unfinished PARTs

- **V22_QR_ANTIBAN_RULES.md** (V22) — 1 commit(s); missing: PART 1
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V22_QR_ANTIBAN_RULES.md`
- **V25_HELPERS_AND_INBOX_FILTER.md** (V25) — 2 commit(s); missing: PART 3
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V25_HELPERS_AND_INBOX_FILTER.md`
- **V35_ONBOARDING_AND_FIXES.md** (V35) — 5 commit(s); missing: PART 2
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V35_ONBOARDING_AND_FIXES.md`
- **V41_COMPLETION_PASS.md** (V41) — 8 commit(s); missing: PART 0
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V41_COMPLETION_PASS.md`
- **V47_COMPREHENSIVE_CLOSEOUT.md** (V47) — 5 commit(s); missing: PART 6
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V47_COMPREHENSIVE_CLOSEOUT.md`
- **V48_UNIFIED_ACCOUNTS_OVERVIEW.md** (V48) — 4 commit(s); missing: PART 5
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V48_UNIFIED_ACCOUNTS_OVERVIEW.md`

## Imports that resolve to nothing — 1 in production code, 0 in tests

**Production code:**

- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\product_reports.py`:172 — imports app.services.product_ai_merge — no such module

## Functions with no implementation — 0 in production code, 108 in tests

_No production-code occurrences._

<details><summary>108 occurrence(s) in test files (mocks/stubs — usually benign)</summary>

- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_chatprofile.py`:72 — def raise_for_status() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_chatprofile.py`:76 — def __init__() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_send_flow.py`:68 — def delete() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_tg_part2.py`:75 — def refresh() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_tg_part3.py`:103 — def rollback() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_tg_part4.py`:79 — def rollback() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v16_part4.py`:32 — def raise_for_status() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v17_part3.py`:51 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v17_part3.py`:53 — def refresh() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v18_part1.py`:136 — def refresh() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v18_part2.py`:66 — def refresh() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v18_part2.py`:67 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v18_part2.py`:166 — def refresh() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v19_part4.py`:265 — def add() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v19_part4.py`:266 — def commit() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v20_part1.py`:43 — def refresh() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v20_part1.py`:44 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v20_part2.py`:45 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v21_handshake_phone_fallback.py`:45 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v21_pending_exclusion.py`:44 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v21_ratio_cap.py`:46 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v25_part1.py`:270 — def flush() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v25_part1.py`:272 — def refresh() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v26_part2.py`:139 — def rollback() has no implementation
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\tests\test_v26_part4.py`:72 — def add() has no implementation
- _...and 83 more_

</details>

---

# بیهوده‌ها / Useless

## Orphan source files — 21

- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\account_schedules.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\ai_keys.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\contact_groups.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\files.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\journals.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\keyword_rules.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\status_schedules.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\templates.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\api\v1\wa_collections.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\app\services\warmup_daily_variety.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\migrations\env.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts\diag_688862_inbox_20260729.py` — not imported anywhere and not tied to any prompt; also UNTRACKED
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts\diag_batch_status_20260729.py` — not imported anywhere and not tied to any prompt; also UNTRACKED
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts\diag_focus_20260729.py` — not imported anywhere and not tied to any prompt; also UNTRACKED
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts\diag_newconn_yellowcard_20260729.py` — not imported anywhere and not tied to any prompt; also UNTRACKED
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts\merge_product_mentions_once.py` — not imported anywhere and not tied to any prompt; also UNTRACKED
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\backend\scripts_backfill_helper_phones.py` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\postcss.config.js` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\src\components\PlatformSwitcher.test.js` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\tailwind.config.js` — not imported anywhere and not tied to any prompt
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\frontend\vite.config.js` — not imported anywhere and not tied to any prompt

## Byte-identical duplicate source files — 0

_None._

## Byte-identical duplicate PROMPT files — 1 group(s)

- SHA256 `4a20e02ab01269ce` — 2 identical copies (77,914 bytes each):
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\New Text Document (2).txt`
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\V14_MASTER_PROMPT.md`
  - **Only one of these is the real prompt; the rest are scratch copies inflating the corpus.**

---

# فراموش‌شده‌ها / Forgotten

Prompts with **zero** commits and **zero** code markers — 13:

- **AFRAKALA_ASSISTANT_SYNC.md** — Bring the "پرتکرار محصولات" display at /pricing/market-intelligence fully up to date with the WhatsA
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\AFRAKALA_ASSISTANT_SYNC.md`  (0 imperative requirement line(s), 0 PART(s) — none delivered)
- **CAMPAIGN_CUSTOMIZE_PROMPT.md** — AUTONOMOUS EXECUTION
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\CAMPAIGN_CUSTOMIZE_PROMPT.md`  (1 imperative requirement line(s), 0 PART(s) — none delivered)
- **CLAUDE_CODE_MASTER_PROMPT.md** — PHASE 0 — Git Setup
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\CLAUDE_CODE_MASTER_PROMPT.md`  (0 imperative requirement line(s), 0 PART(s) — none delivered)
- **CLAUDE_CODE_PROMPT_V2.md** — CONTEXT
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\CLAUDE_CODE_PROMPT_V2.md`  (0 imperative requirement line(s), 0 PART(s) — none delivered)
- **COMBINED_STATUS_AND_FILTER.md** — Do two things in order.
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\COMBINED_STATUS_AND_FILTER.md`  (0 imperative requirement line(s), 0 PART(s) — none delivered)
- **CONTACT_SELLERS_PROMPT.md** — AUTONOMOUS EXECUTION
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\CONTACT_SELLERS_PROMPT.md`  (3 imperative requirement line(s), 0 PART(s) — none delivered)
- **GREEN_API_COMPLETION_PROMPT.md** — AUTONOMOUS EXECUTION MODE
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\GREEN_API_COMPLETION_PROMPT.md`  (13 imperative requirement line(s), 0 PART(s) — none delivered)
- **GROUPS_FIX_PROMPT.md** — EXECUTION CONTRACT
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\GROUPS_FIX_PROMPT.md`  (2 imperative requirement line(s), 0 PART(s) — none delivered)
- **NUMBERING_ACCOUNT_CHECK_PROMPT.md** — AUTONOMOUS EXECUTION
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\NUMBERING_ACCOUNT_CHECK_PROMPT.md`  (1 imperative requirement line(s), 0 PART(s) — none delivered)
- **New Text Document (2).txt** — Environment (verified — use as-is, do not re-discover)
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\New Text Document (2).txt`  (11 imperative requirement line(s), 0 PART(s) — none delivered)
- **New Text Document.txt** — 🎯 Project Context (Brief)
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\New Text Document.txt`  (3 imperative requirement line(s), 6 PART(s) — none delivered)
- **project_prompt.txt** — شما به عنوان یک "معمار ارشد نرم‌افزار و متخصص DevOps"، وظیفه دارید یک پروژه کامل نرم‌افزاری (شامل فر
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\project_prompt.txt`  (0 imperative requirement line(s), 0 PART(s) — none delivered)
- **prompt_analysis.txt** — شما یک مهندس ارشد نرم‌افزار و تحلیلگر سیستم هستید.
  - `C:\Users\AFRA\Desktop\bots\claudegreenapi\prompt_analysis.txt`  (0 imperative requirement line(s), 0 PART(s) — none delivered)

## Prompt specs never committed to git — 18

- `C:\Users\AFRA\Desktop\bots\claudegreenapi\AFRAKALA_ASSISTANT_SYNC.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\COMBINED_STATUS_AND_FILTER.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\New Text Document.txt`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V39_UNIVERSAL_COOLDOWN_AND_ELIGIBILITY_GATE.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V40_STORY_PRODUCT_ANALYSIS.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V41_COMPLETION_PASS.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V41_PATH_B_AUTOMATED_WAIT.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V41_RECOVERY_REWARM.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V42_SELFHEALING_MODEL_DISCOVERY.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V43_REPORTING_FILTER_EXPANSION.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V44_MERGE_VERIFY_AND_SEARCH.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V45_EXCLUSION_AND_ACTIVE_CONTACTS.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V47_COMPREHENSIVE_CLOSEOUT.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V48_UNIFIED_ACCOUNTS_OVERVIEW.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V49_RETENTION_AND_DETECTION_FIX.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\V50_STORY_FETCH_RESILIENCE.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\project_prompt.txt`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\prompt_analysis.txt`

## Code shipped with NO surviving prompt spec — 10

The inverse of a forgotten prompt: work that was committed and lives in the codebase, but whose specification file does not exist. Nobody can now say what these were scoped to deliver.

| Version | Commits | Files carrying the marker |
|---|---|---|
| **V23** | 2 | 6 |
| **V24** | 1 | 12 |
| **V26** | 5 | 25 |
| **V31** | 1 | 2 |
| **V34** | 1 | 3 |
| **V36** | 3 | 17 |
| **V37** | 2 | 0 |
| **V38** | 2 | 14 |
| **V51** | 1 | 3 |
| **V52** | 1 | 1 |

---

# نقشه پرامپت‌ها / Prompt map

| Prompt file | Goal (summary) | Status | Commits | Output file(s) |
|---|---|---|---|---|
| `V3_MASTER_PROMPT.md` | EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V4_MASTER_PROMPT.md` | EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V5_MASTER_PROMPT.md` | EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V6_MASTER_PROMPT.md` | EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V7_MASTER_PROMPT.md` | EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V8_MASTER_PROMPT.md` | EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V9_MASTER_PROMPT.md` | EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V10_MASTER_PROMPT.md` | EXECUTION CONTRACT | **NO TRACE** | 0 | — |
| `V11_MASTER_PROMPT.md` | AUTONOMOUS EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V12_MASTER_PROMPT.md` | AUTONOMOUS EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V13_MASTER_PROMPT.md` | AUTONOMOUS EXECUTION CONTRACT | **UNVERIFIABLE** | 0 | — |
| `V14_MASTER_PROMPT.md` | Environment (verified — use as-is, do not re-discover) | **UNVERIFIABLE** | 0 | — |
| `V15_BUGFIX_UX_PROMPT.md` | Environment (same as V14 — verified) | **UNVERIFIABLE** | 0 | — |
| `V16_MASTER_PROMPT.md` | 0. CONTEXT (read first, do not skip) | **COMPLETE** | 6 | `NGROK_SERVICE_SETUP.md`, `adlinks.py`, `campaigns.py` +24 |
| `V17_AUTO_WARMUP_MESH_PROMPT.md` | Automatic, AI-driven, mesh-based warm-up + typing simulation | **COMPLETE** | 6 | `campaigns.py`, `warmup.py`, `webhook.py` +19 |
| `V18_FIX_FANOUT_AND_WARMUP_WIRING.md` | Fix silent multi-account fan-out + wire the "smart warm-up" toggle ... | **COMPLETE** | 2 | `accounts.py`, `campaigns.py`, `account_selection.py` +5 |
| `V19_GROUP_WARMUP_PROMPT.md` | Group-based warm-up: add cold numbers to admin-owned groups (ADD to... | **COMPLETE** | 5 | `warmup.py`, `main.py`, `__init__.py` +10 |
| `V20_FIX_TOGGLE_AND_WARM_PEERS.md` | Fix stuck warm-up toggle + make existing warm accounts usable as me... | **COMPLETE** | 3 | `accounts.py`, `warmup.py`, `main.py` +6 |
| `V21_RATIO_AND_BREAKER.md` | Enforce warm:cold ratio, exclude unconnected accounts, smarter chai... | **COMPLETE** | 5 | `warmup.py`, `green_api.py`, `warmup_dashboard.py` +6 |
| `V22_QR_ANTIBAN_RULES.md` | Show anti-ban rules on the QR-scan screen (pre-scan + scan-moment r... | **PARTIAL** | 1 | `package.json`, `QrAntibanRules.jsx`, `qrAntibanRules.js` +2 |
| `V25_HELPERS_AND_INBOX_FILTER.md` | Automatic "human helpers" warm-up assist (≤25 known people) + inbox... | **PARTIAL** | 2 | `warmup_helpers.py`, `webhook.py`, `main.py` +9 |
| `V27_ANTIBAN_HARDENING.md` | Anti-ban hardening: peer-health gating, peer-level rate limits, min... | **COMPLETE** | 10 | `accounts.py`, `campaigns.py`, `warmup.py` +22 |
| `V28_FLEXIBLE_OUTREACH_ASSISTANT.md` | Flexible multi-sender AI-personalized outreach assistant (generaliz... | **COMPLETE** | 5 | `warmup_helpers.py`, `main.py`, `__init__.py` +4 |
| `V29_TEAM_COLLABORATION_REVISED.md` | «همکاری تیمی» (Team Collaboration): full personnel-outreach warm-up... | **COMPLETE** | 11 | `New Microsoft Visio Drawing.vsdx`, `New Text Document (2).txt`, `V13_MASTER_PROMPT.md` +34 |
| `V30_TEAM_COLLAB_REFINEMENTS.md` | Complete «همکاری تیمی» frontend + 10 refinements (pacing, variety, ... | **COMPLETE** | 9 | `V30_TEAM_COLLAB_REFINEMENTS.md`, `dashboard.py`, `warmup_helpers.py` +23 |
| `V33_STALL_FIX_AND_REMINDER_CAP.md` | Fix the pending-stall root cause, enforce the 2-cold-account ceilin... | **COMPLETE** | 5 | `V33_STALL_FIX_AND_REMINDER_CAP.md`, `warmup_helpers.py`, `main.py` +5 |
| `V35_ONBOARDING_AND_FIXES.md` | Stop auto-status, contact categories, guided onboarding wizard, das... | **PARTIAL** | 5 | `V35_ONBOARDING_AND_FIXES.md`, `dashboard.py`, `onboarding.py` +23 |
| `V39_UNIVERSAL_COOLDOWN_AND_ELIGIBILITY_GATE.md` | Two permanent, system-enforced rules: universal connect-cooldown + ... | **COMPLETE** | 5 | `accounts.py`, `partner.py`, `warmup_helpers.py` +17 |
| `V40_STORY_PRODUCT_ANALYSIS.md` | Story product analysis: new tab inside Stories, AI text/image detec... | **COMPLETE** | 11 | `.gitignore`, `reporting.py`, `reports_public.py` +23 |
| `V41_COMPLETION_PASS.md` | Recovery re-warm of 7105325764 via the existing mesh engine, per Gr... | **PARTIAL** | 8 | `warmup.py`, `warmup_helpers.py`, `webhook.py` +17 |
| `V41_PATH_B_AUTOMATED_WAIT.md` | Do not relax any rule; automatically apply the recovery enrollment ... | **COMPLETE** | 8 | `warmup.py`, `warmup_helpers.py`, `webhook.py` +17 |
| `V41_RECOVERY_REWARM.md` | Recovery re-warm of 7105325764 via the existing mesh engine, per Gr... | **COMPLETE** | 8 | `warmup.py`, `warmup_helpers.py`, `webhook.py` +17 |
| `V42_PART1_INVENTORY.md` | The AI key pool / provider abstraction (the thing to extend, not re... | **COMPLETE** | 6 | `V42_PART1_INVENTORY.md`, `ai_model_discovery.py`, `ai_vision_model_cache.py` +3 |
| `V42_SELFHEALING_MODEL_DISCOVERY.md` | Self-healing AI model selection: discover live, working vision mode... | **COMPLETE** | 6 | `V42_PART1_INVENTORY.md`, `ai_model_discovery.py`, `ai_vision_model_cache.py` +3 |
| `V43_REPORTING_FILTER_EXPANSION.md` | Expand the reporting page's date-range and product-count filters | **COMPLETE** | 4 | `reports_public.py`, `product_reports.py`, `Reporting.jsx` +2 |
| `V44_MERGE_VERIFY_AND_SEARCH.md` | Verify/fix product-name merging in the top-products report + add se... | **COMPLETE** | 4 | `reporting.py`, `product_match.py`, `product_reports.py` +2 |
| `V45_EXCLUSION_AND_ACTIVE_CONTACTS.md` | Exclude our own numbers from product detection + harvest an active-... | **COMPLETE** | 4 | `active_contacts.py`, `own_numbers.py`, `reporting.py` +15 |
| `V47_COMPREHENSIVE_CLOSEOUT.md` | Comprehensive close-out: own-number cleanup + async story-analysis ... | **PARTIAL** | 5 | `statuses.py`, `story_backlog.py`, `tasks.py` +12 |
| `V48_PART1_INVENTORY.md` | 1. `/accounts` (Accounts.jsx) | **COMPLETE** | 4 | `V48_PART1_INVENTORY.md`, `accounts.py`, `incidents.py` +13 |
| `V48_UNIFIED_ACCOUNTS_OVERVIEW.md` | Unified "all accounts at a glance" status page | **PARTIAL** | 4 | `V48_PART1_INVENTORY.md`, `accounts.py`, `incidents.py` +13 |
| `V49_RETENTION_AND_DETECTION_FIX.md` | Fix the 2-day data purge + reconcile date-range UI + close a detect... | **COMPLETE** | 4 | `reporting.py`, `reports_public.py`, `product_match.py` +5 |
| `V50_STORY_FETCH_RESILIENCE.md` | Scheduled auto-fetch for stories + multi-account resilience | **COMPLETE** | 3 | `story_fetch.py`, `celery_app.py`, `tasks.py` |
| `AFRAKALA_ASSISTANT_SYNC.md` | Bring the "پرتکرار محصولات" display at /pricing/market-intelligence... | **NOT DONE** | 0 | — |
| `CAMPAIGN_CUSTOMIZE_PROMPT.md` | AUTONOMOUS EXECUTION | **NOT DONE** | 0 | — |
| `CLAUDE_CODE_MASTER_PROMPT.md` | PHASE 0 — Git Setup | **NOT DONE** | 0 | — |
| `CLAUDE_CODE_PROMPT_V2.md` | CONTEXT | **NOT DONE** | 0 | — |
| `COMBINED_STATUS_AND_FILTER.md` | Do two things in order. | **NOT DONE** | 0 | — |
| `CONTACT_SELLERS_PROMPT.md` | AUTONOMOUS EXECUTION | **NOT DONE** | 0 | — |
| `GREEN_API_COMPLETION_PROMPT.md` | AUTONOMOUS EXECUTION MODE | **NOT DONE** | 0 | — |
| `GROUPS_FIX_PROMPT.md` | EXECUTION CONTRACT | **NOT DONE** | 0 | — |
| `New Text Document (2).txt` | Environment (verified — use as-is, do not re-discover) | **NOT DONE** | 0 | — |
| `New Text Document.txt` | 🎯 Project Context (Brief) | **NOT DONE** | 0 | — |
| `NUMBERING_ACCOUNT_CHECK_PROMPT.md` | AUTONOMOUS EXECUTION | **NOT DONE** | 0 | — |
| `project_prompt.txt` | شما به عنوان یک "معمار ارشد نرم‌افزار و متخصص DevOps"، وظیفه دارید ... | **NOT DONE** | 0 | — |
| `prompt_analysis.txt` | شما یک مهندس ارشد نرم‌افزار و تحلیلگر سیستم هستید. | **NOT DONE** | 0 | — |

---

# Summary

- Complete: **23**
- Partial: **6**
- Not done: **13**
- Half-done code findings: **109**
- Orphan files: **21**  |  Duplicate files: **0**
- Prompt specs untracked by git: **18**
