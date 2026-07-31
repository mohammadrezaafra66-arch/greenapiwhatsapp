# Project State Report — 2026-07-31

Every figure below was measured on this date. Where something was not measured, it says so
rather than estimating.

---

## V52 cleanup — COMPLETE

| | |
|---|---|
| Branch | `afrapayam-redesign`, **0 ↔ 0** with origin |
| Commits | 6 clean V52 commits (`2c1b66f` … `a5f3920`) |
| Tests | **1401 passed / 2 failed** |
| Specs rescued | 13 (V39–V50); 15 `V*` spec files now in HEAD |
| Audit tooling | `deep_audit.py`, `audit.md`, `FULL_PROJECT_AUDIT.md`, `CLAUDE.md` |
| Junk removed | 6 files, **1,207,070 bytes** |
| Untracked | 46 → 11 |
| Junk commit `0fc8aa7` | Not reachable from the branch |

### Commits

```
a5f3920  V52 PART 6: document design decisions and lessons
4d4cdbb  V52 PART 5: gitignore generated test/audit artifacts
95cca74  V52 PART 4: keep the canonical key deterministic and always on
155537e  V52 PART 3: commit orphaned V39-V50 specs + audit tooling
6c29b95  V52 PART 2: AI-assisted product merge, gated behind ai_merge
2c1b66f  V52 PART 1: config.extra=ignore + product_ai_merge service + test
```

---

## Test baseline — FRAGILE, and `origin/main` is not green

**Measured on `afrapayam-redesign`:** 1401 passed / 2 failed.

**Measured on `origin/main` (`5f7d944`):** only the two suspect tests were run there. Both
**fail**, with byte-identical assertions:

```
tests/test_v45_part2.py:245   assert (None is not None)
tests/test_v49_part4.py:92    assert 3 == 2
```

> **Not measured:** the full suite on `origin/main`. Do not assume it is 1401/2 — `main`
> predates V52 and collects fewer tests. The V51 PART 1 commit message claims 1394 passing;
> that figure is **not reproducible today** because these 2 tests fail on that commit.

Both failures query the live database with `limit=1000` and assert exact counts, so they are
sensitive to data volume and wall-clock date. They rotted between 2026-07-26 and 2026-07-31.
They are environmental, not caused by any V52 change, and should be triaged separately by
making them hermetic.

---

## Open items

| Issue | Impact | Effort |
|---|---|---|
| Frontend image stale — no volume mount, image predates the rebrand by ~20h | **Rebrand not visible on :3002** | ~5 min rebuild |
| `New Text Document (2).txt` tracked — 77,914 bytes, byte-identical to `V14_MASTER_PROMPT.md` (SHA256 `4a20e02ab01269ce`), committed in the V29 era | Clutter | ~1 min |
| 11 untracked files awaiting a keep/delete decision | Clutter | ~5 min |
| V45/V49 data rot | Test reliability | 1–4 h |
| 10 versions with no spec: V23, V24, V26, V31, V34, V36, V37, V38, V51, V52 | Documentation debt | Varies |

**V26 is the priority of that last row** — 5 commits, 25 files carrying its marker, including
Whisper voice transcription. The branch `claude/whatsapp-group-voice-v26-k93pir` was checked and
contains no V26 spec, so it was never written rather than lost.

---

## Next phase

### Phase A — now

1. **Rebuild the frontend image.** The container mounts nothing; the running image was built
   2026-07-29 16:13 UTC, the rebrand landed 2026-07-30 12:00 UTC. Until rebuilt, :3002 serves
   the pre-rebrand UI regardless of what is in git.
   ```
   docker compose up -d --build frontend
   ```
   Then verify visually.
2. **Decide the 11 untracked files** (see below).
3. Optionally remove the tracked V14 duplicate.

### Phase B — this week

1. Merge `afrapayam-redesign` → `main` when approved. Note that `main` currently fails the same
   2 tests, so this merge does not make `main` worse.
2. Triage V45/V49: replace live-DB queries with fixtures.
3. Decide what ships next. **`V16_MASTER_PROMPT.md` is not it** — it declares a V15/237-test
   baseline and its six PARTs shipped on 2026-07-15.

### Phase C — ongoing

1. Spec discipline: from V53 on, the spec lands in the same commit as the code.
2. Re-measure the test baseline periodically and record the date alongside the number.

---

## Untracked files awaiting decision — 11

The zips, `diag_*.py` scripts and `ui-research/` referenced in earlier notes are now covered by
`.gitignore` and no longer appear here.

| File | Guess |
|---|---|
| `AFRAKALA_ASSISTANT_SYNC.md` | Working doc |
| `COMBINED_STATUS_AND_FILTER.md` | Working doc |
| `MENU_SIDEBAR_RESEARCH.md` | Working doc |
| `OPEN_TO_LAN.md` | Working doc |
| `V52_CLEANUP_REPORT_20260731.md` | This session's output |
| `project_prompt.txt` | Prompt scratch |
| `backend/scripts/merge_product_mentions_once.py` | One-off migration |
| `backend/scripts/v40_reanalyze_eligible.py` | One-off migration |
| `check_account.py` | Utility |
| `check_team_collab.ps1` | Utility |
| `find_phone_across_dbs.ps1` | Utility |

No action taken on these — they may be active work, and deletion is not reversible.

---

## Summary

| Component | Status |
|---|---|
| Codebase | ✅ 6 clean commits, pushed |
| Tests | ✅ 1401 / 2 (both pre-existing) |
| Specs | ✅ 13 rescued and committed |
| Junk | ✅ 1.2 MB removed |
| Branch sync | ✅ 0 divergence |
| Ready to merge | ✅ Subject to review |
| Ready for production | ⏳ **Frontend image must be rebuilt first** |
