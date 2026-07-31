# V17 Roadmap — Decision Framework

**Date:** 2026-07-31
**Status:** Post-V52 (rebrand + spec rescue + merge to `main` complete)

---

## Where the project actually is

| | |
|---|---|
| `main` | `0d9adbb`, pushed, **1401 passed / 2 failed** |
| Versions shipped | 52 |
| Commits | 269 |
| Frontend | Rebrand live and content-verified at `192.168.170.8:3002` |
| Specs | 13 rescued (V39–V50); **10 versions still have none** |

### What V52 delivered

- AfraPayam rebrand across the frontend (58 files)
- Opt-in AI-assisted product merge, correctly gated
- 13 orphaned specs committed — they existed on one machine only
- Static audit tooling (`deep_audit.py`) that runs without an API key
- 1.2 MB of junk removed; one 50-file sweep commit rewritten into ten scoped ones

---

## Decision: Operational Excellence, not a V17 feature wave

### Why

The blocker is not missing features. It is that **the project cannot currently prove its own
state**, and this session produced three concrete demonstrations of that:

1. **The test baseline was not trustworthy.** The V51 commit claims "1387 → 1394, zero
   regressions". Run today, that commit fails 2 tests. A baseline nobody re-measures is not a gate.
2. **Ten versions have no specification.** V23, V24, V26, V31, V34, V36, V37, V38, V51, V52. V26
   alone is 5 commits and 25 files including Whisper voice transcription. Nobody can now state what
   it was scoped to do, which makes changing it risky.
3. **Irreplaceable work sat untracked.** 13 specs were one `git clean -fd` from permanent loss.

Adding features on top of this increases the surface area of what cannot be verified.

### Immediate actions, in priority order

| # | Action | Why first | Effort |
|---|---|---|---|
| 1 | ~~Fix V45/V49~~ | ✅ **DONE 2026-07-31** — `main` is green at **1403/0**, verified over 3 runs. See `V45_V49_ROOT_CAUSE_AND_FIX.md` | — |
| 2 | Reconstruct the V26 spec from its 5 commits and 25 marked files | Largest undocumented subsystem | 2–4 h |
| 3 | Write specs for V51 and V52 | Recent enough to reconstruct accurately | 1–2 h |
| 4 | Archive shipped prompts into `archive/` | `V16_MASTER_PROMPT.md` (V15 baseline, shipped 2026-07-15) is still in the root and was mistakenly targeted for execution twice today | 15 min |
| 5 | Remaining specs: V23, V24, V31, V34, V36, V37, V38 | Older, lower value, harder to reconstruct | 4–8 h |

### Revisit the feature question after

Two to four weeks of a green, stable baseline. At that point "what ships next" can be answered
against a codebase whose state is verifiable.

---

## V45/V49 — diagnosed, no longer speculative

Earlier notes called this "database content rot". The actual measurement
(`backend/scripts/v45_v49_root_cause_diag.py`) shows two **different** and specific defects:

### V45 — `limit` truncation

```
rows in 2-day window        : 2,034
DISTINCT product_name       : 1,304
test limit                  : 1,000
→ 304 products fall outside the limit
```

The test inserts a fixture with `mention_count=1` and asserts it appears in
`top_products_rows(days=2, limit=1000)`. With 1,304 distinct products competing and results ordered
by `mention_count DESC`, a count of 1 **cannot** rank in the top 1000. The assertion
`assert f is not None` fails for arithmetic reasons, not detection-logic reasons.

**Fix:** the test must not compete with live data. Either scope the query to its own
`instance_id`, or use a fake DB as `test_v44_part2_grouping_fix.py` already does.

### V49 — fixture name collides with production data

```
leftover rows matching the fixture product name: 1
   instance_id='7105325764'  →  1 row
```

`7105325764` is the **real Green API instance**, not a test instance. The test cleans up with
`DELETE ... WHERE instance_id = 'v49p4_test_inst'`, so this genuine production row survives, merges
into the same product group, and turns the expected count of 2 into 3.

**Fix:** either make the fixture product name unique enough that no real listing can collide (as
`test_v45_part2.py` attempts with its `V45TESTPROD` prefix), or filter the assertion by
`instance_id`.

### Shared root defect

Both tests **assert exact counts against a live, shared, growing table they do not control**. That
is the class of bug, and it will recur in any new test written the same way.

---

## Recommended discipline going forward

1. A spec file lands in the **same commit** as the code it describes. No exceptions from V53 on.
2. Tests that assert exact counts must own their data — fixtures or an `instance_id` scope.
3. Record a test baseline **with the date it was measured**. An undated count is not a baseline.
4. Archive a master prompt the moment its parts ship, so no stale prompt is executable by accident.
