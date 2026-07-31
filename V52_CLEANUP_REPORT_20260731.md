# V52 Cleanup Session — Final Report

**Date:** 2026-07-31
**Branch:** `afrapayam-redesign` → `origin/afrapayam-redesign`
**Final state:** 0 divergence, working tree clean of tracked changes

---

## Timeline

| Stage | Event |
|---|---|
| Found | `0fc8aa7` — a 50-file `git add -A` sweep carrying 1.1 MB of unrelated files, message describing one fix |
| Escalated | The commit reached the remote mid-session |
| Resolved | Rewritten as 4 scoped commits; junk removed from the branch |

---

## Results

| | |
|---|---|
| Test suite | **1401 passed / 2 failed** |
| Specs rescued | 13 files (V39–V50), previously in no commit and on no remote |
| Audit tooling | `deep_audit.py`, `audit.md`, `FULL_PROJECT_AUDIT.md`, `status_complete.ps1` |
| Junk deleted | 6 files, **1,207,070 bytes** |
| Untracked files | 46 → 10 |
| Junk commit | `0fc8aa7` no longer reachable from the branch |

### Commits on the branch

```
4d4cdbb  V52 PART 5: gitignore generated test/audit artifacts and scratch files
95cca74  V52 PART 4: keep the canonical key deterministic and always on
155537e  V52 PART 3: commit orphaned V39-V50 specs + audit tooling
6c29b95  V52 PART 2: AI-assisted product merge, gated behind ai_merge
2c1b66f  V52 PART 1: config.extra=ignore + product_ai_merge service + test
74a6074  AfraPayam rebrand + light design system
```

---

## The design conclusion that took two attempts

The AI-merge feature has **two** merge passes, and they must not share one flag:

| Pass | Nature | Gating |
|---|---|---|
| `product_canonical_key` | Deterministic. Merges spelling/shorthand variants, keeps distinct model cores apart | **Always on** |
| `_collapse_by_alias` + `product_ai_merge` | Non-deterministic, calls an AI provider | **Gated behind `ai_merge`** |

Gating *both* made the report under-merge. Setting `ai_merge=True` to compensate ran the AI pass,
which merged SMS46NI01 into SMS46NW01 → `assert 17 == 13`, the exact over-merge
`test_bosch_dishwasher_shorthand_merges_keeps_other_models_distinct` exists to catch. Only the
split above satisfies every test.

**A correction is recorded here deliberately:** the gating change in PART 2 was made on the
inference that the canonical key caused the V45/V49 failures. That inference was wrong, was
disproven by experiment, and PART 4 reverts it. See below.

---

## Remaining failures — pre-existing, proven by experiment

Both tests were checked out at `5f7d944` (`origin/main`, before this feature existed) and re-run:

| Test | On `origin/main` |
|---|---|
| `test_v45_part2.py::test_report_filters_preexisting_own_number_rows` | **FAILS** — `assert (None is not None)` |
| `test_v49_part4.py::test_v49_detection_report_exclusion_and_retention_end_to_end` | **FAILS** — `assert 3 == 2` |

Both hit the **real database** with `limit=1000`, making them sensitive to live data volume and
wall-clock date. They rotted between 2026-07-26 and 2026-07-31.

**Consequence: `origin/main` is not green.** The V51 PART 1 commit message claims
"1387 → 1394, zero regressions"; that commit fails these 2 tests when run today. The 1394 figure
is not reproducible.

---

## Still open

1. **`New Text Document (2).txt`** is tracked in the branch — 77,914 bytes, byte-identical to
   `V14_MASTER_PROMPT.md` (SHA256 `4a20e02ab01269ce`). Committed in the V29 era, unrelated to this
   session's sweep.
2. **10 untracked files** deliberately left alone pending a decision: 4 working docs
   (`AFRAKALA_ASSISTANT_SYNC.md`, `COMBINED_STATUS_AND_FILTER.md`, `MENU_SIDEBAR_RESEARCH.md`,
   `OPEN_TO_LAN.md`), 5 utility scripts, and `project_prompt.txt`.
3. **Frontend still serves a stale build.** The container has no volume mount; its image predates
   the rebrand by ~20 hours. Needs `docker compose up -d --build frontend`.
4. **10 versions have no spec at all** — V23, V24, V26, V31, V34, V36, V37, V38, V51, V52. The
   remote branch `claude/whatsapp-group-voice-v26-k93pir` was checked and does **not** contain a
   V26 spec, confirming it was never written. V26 is the worst case: 5 commits, 25 files, including
   Whisper voice transcription.
5. **V45/V49 data-rot** should be triaged on its own — most likely by making those tests
   hermetic instead of querying live data with `limit=1000`.

### Note on "continue with V16"

`V16_MASTER_PROMPT.md` declares a baseline of **V15, 237 tests**. The codebase is at **V52** with
1403 tests. Its six PARTs were delivered in 2026-07-15 (`239c51c`…`455cc5a`). Running it now would
re-implement finished work. It is not a valid next step.

---

*Reproduce the prompt-vs-code analysis with:* `python deep_audit.py --output audit.md`
