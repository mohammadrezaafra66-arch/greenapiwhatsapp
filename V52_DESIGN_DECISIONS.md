# V52 Design Decisions & Lessons

Recorded 2026-07-31 so these are not re-derived. Every claim here was verified by running
the command, not inferred.

---

## 1. AI-merge gating — two passes cannot share one flag

`top_products_rows` has **two** independent merge passes. The bug was treating them as one.

| Pass | Nature | Correct gating |
|---|---|---|
| `product_canonical_key` | Deterministic. Merges spelling/shorthand variants (`SMS46NW01` ↔ `46NW01B`) while keeping distinct model cores apart (`SMS46NI01` stays separate) | **Always on** |
| `_collapse_by_alias` + `product_ai_merge` | Non-deterministic, calls an AI provider | **Gated behind `ai_merge`** |

### What was tried, and exactly how each attempt failed

| Attempt | `product_canonical_key` | AI pass | Bosch test result |
|---|---|---|---|
| Original | always on | gated | **passes** (13) |
| Gated both behind `ai_merge` (PART 2) | off at default | off | **fails — under-merge.** The NW01 spellings never fold together |
| Then `ai_merge=True` to compensate | on | **on** | **fails — `assert 17 == 13`.** The AI pass merges NI01 into NW01 |
| Reverted (PART 4, `95cca74`) | always on | gated | **passes** (13) |

The `17 == 13` failure came from turning the **AI pass** on, not from the canonical key. Those
are two different failures with two different causes, and conflating them sends you in circles.
`test_bosch_dishwasher_shorthand_merges_keeps_other_models_distinct` exists precisely to catch
the over-merge.

### Lesson

A feature flag must gate exactly one behavior. When a flag controls both a deterministic
improvement and a non-deterministic one, no setting of it is correct.

---

## 2. Do not infer a failure's cause — check the base commit

The gating change in PART 2 was made on the belief that the canonical key broke
`test_v45_part2` and `test_v49_part4`. That belief was never tested, and it was wrong.

The check that settled it, in one command:

```bash
git checkout 5f7d944          # origin/main — before this feature existed
pytest tests/test_v45_part2.py::test_report_filters_preexisting_own_number_rows \
       tests/test_v49_part4.py::test_v49_detection_report_exclusion_and_retention_end_to_end
git checkout afrapayam-redesign
```

Both fail there, with byte-identical assertions (`assert (None is not None)`, `assert 3 == 2`).
They are pre-existing and unrelated. Roughly an hour of work followed from skipping this check.

### Lesson

Before attributing a failure to your change, run the failing test on the commit before your
change. If it fails there too, it is not yours.

---

## 3. The test baseline on `origin/main` is not green

The V51 PART 1 commit message claims *"Full suite 1387 -> 1394, zero regressions"*. Running that
exact commit (`5f7d944`) on 2026-07-31 fails the two tests above.

Both query the **live database** with `limit=1000` and assert exact counts. Between 2026-07-26
and 2026-07-31 the data volume and wall-clock date moved, and the assertions rotted.

Practical consequences:

- "1394 passing" is not reproducible and must not be used as a merge gate.
- The current honest baseline on `afrapayam-redesign` is **1401 passed / 2 failed**, where those
  2 are the environmental failures above.
- Fixing them is a separate task: make them hermetic (fixtures instead of live queries), do not
  fold it into feature work.

### Lesson

A test that asserts exact counts against a live, growing database has a shelf life. Record
baselines with the date they were measured.

---

## 4. Untracked is not stored — specs are code

Two failure modes, both real in this repo:

- **Never written.** V23, V24, V26, V31, V34, V36, V37, V38, V51, V52 shipped with no spec at
  all. V26 is the worst: 5 commits, 25 files carrying its marker, including Whisper voice
  transcription. The remote branch `claude/whatsapp-group-voice-v26-k93pir` was checked and does
  not contain one either — it was never written, not merely lost.
- **Written but never committed.** 13 specs (V39–V50) existed only in the working directory,
  on one machine, backed up nowhere.

`git clean -fd` deletes untracked files with **no reflog and no recovery**. It was proposed
during this session while those 13 specs were untracked. Running it would have destroyed the
only copies.

Fixed in `155537e`: all 13 specs plus `CLAUDE.md` and the audit tooling are now committed.

### Lesson

If losing a file would hurt, commit it. `.gitignore` is for artifacts you can regenerate, not
storage. Before any `git clean`, run `git clean -nd` and read the list.

---

## 5. `git add -A` produces commits that lie

Commit `0fc8aa7` was titled *"PART 1: Fix AI-merge gating — canonical key default"* and
contained **50 files**, including:

```
project_structure.txt        1,144,900 bytes
New Text Document.txt           26,743
analysis_report.md              26,676
analyze_project.py, test_deepseek.py, 6 × diag_*.py, ui-research/
```

The message described one change; the commit made fifty. Once such a commit is pushed, the
blob is in the repository permanently unless history is rewritten.

Rewritten here into four scoped commits (`6c29b95`, `155537e`, `95cca74`, `4d4cdbb`).

### Lesson

Stage by path, not with `-A`. The commit message and the diff must describe the same change.

---

## 6. `--force-with-lease`, never bare `--force`

`0fc8aa7` reached the remote mid-session. Local had already rewritten it, so the branch
diverged 1 ↔ 4. `--force-with-lease` was the correct tool because:

- it is a feature branch, not `main`
- the junk commit was minutes old, not historical
- the lease aborts if anyone pushed between fetch and push

Bare `--force` skips that last check and would silently discard an unseen push.

### Lesson

`--force-with-lease` always. And `git fetch` before any remote operation — this repo saw
concurrent pushes from another process three separate times during one session.

---

## 7. Check a prompt's baseline before executing it

`V16_MASTER_PROMPT.md` declares *"Current baseline: V15, 237 tests passing"*. The codebase is at
V52 with 1403 tests. Its six PARTs shipped on 2026-07-15 (`239c51c` … `455cc5a`). Executing it
would re-implement finished work and commit over it.

Three cheap staleness checks:

1. Baseline test count in the prompt vs. actual (`237` vs `1403`)
2. Prompt version vs. `git log --oneline | head` (`V16` vs `V52`)
3. `git log --grep="V16 PART"` — did its parts already ship? (yes, all six)

### Lesson

In a project moving this fast, a two-week-old prompt is probably stale. Check before running,
not after.

---

## Quick reference

**Do**

- Commit specs in the same commit as the code they describe
- `git fetch` before every remote operation
- Verify a failure on the base commit before attributing it to your change
- Stage by explicit path
- Record test baselines with their measurement date

**Do not**

- Run `git clean -fd` without reading `git clean -nd` first
- Use `git add -A` for a targeted fix
- Use bare `git push --force`
- Gate two independent behaviors behind one flag
- Trust a commit message's test count without re-running it
