# FULL PROJECT AUDIT — AfraPayam / Afrakala WhatsApp Sender

Consolidated status as of **2026-07-31**. Sources: live `git`, running Docker containers,
a full container test run, `deep_audit.py` (static prompt-vs-code analysis) and
`status_complete.ps1` (git/version inventory). Every claim below was executed, not assumed.

Companion documents:

- `C:\Users\AFRA\Desktop\bots\claudegreenapi\audit.md` — per-prompt detail, 55 prompts
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\deep_audit.py` — regenerates `audit.md`
- `C:\Users\AFRA\Desktop\bots\claudegreenapi\status_complete.ps1` — git/version inventory

---

## 1. Executive summary

| Area | State |
|---|---|
| Product maturity | V52; 258 commits; 50 V-tagged versions |
| Test suite | 1403 collected — **6 failed / 1397 passed** (stale, see §5) |
| Running services | 7 `claudegreenapi-*` containers, up 16h, API HTTP 200 |
| V50 story fetch | **Live and healthy** — 392 successful runs, every 30 min |
| Branch hygiene | ✅ **Resolved** — HEAD restored to `afrapayam-redesign` |
| Working tree | ✅ **Import repaired** |
| Specification hygiene | ⚠ 10 shipped versions have no surviving spec; 18 specs untracked |

Two problems need a decision. Everything else is healthy or cosmetic.

---

## 2. Git state — RESOLVED 2026-07-31

> **Update:** `git checkout afrapayam-redesign` was executed and verified. All 5 uncommitted
> files carried across untouched, `product_ai_merge.py` (6,649 bytes) is restored,
> `config.py` has `extra = "ignore"` again, and the import resolves (`IMPORT OK`). Nothing
> was stashed or lost. The section below records the problem as it was found.

### Original finding

```
  afrapayam-redesign  2c1b66f  V52 PART 1: commit config.extra=ignore + product_ai_merge service + test
* main                5f7d944  V51 PART 1: auto-analyze story backlog after each scheduled fetch
```

`git log main..afrapayam-redesign` — **two commits are stranded off the checked-out branch**:

| Commit | Contents |
|---|---|
| `2c1b66f` | `config.py` +1, `product_ai_merge.py` +165, `test_product_ai_merge.py` +110 |
| `74a6074` | AfraPayam rebrand — 58 frontend files |

### Consequence: a dangling import

```
backend\app\services\product_reports.py:172
    from app.services.product_ai_merge import ai_product_merge_aliases
```

`Test-Path backend\app\services\product_ai_merge.py` → **False** on `main`.

Severity is **moderate, not critical**: the import is lazy and wrapped in
`try/except Exception`, so it degrades silently rather than crashing. The effect is that the
AI-merge path is permanently dead on this branch while appearing to be wired up.

### The fix is safe — verified

The branches differ in 61 files. None overlap the 5 uncommitted backend files:

```
NO COLLISION — all 5 uncommitted files are identical on both branches; checkout is safe
```

`git checkout afrapayam-redesign` carries the uncommitted work across untouched, restores
`product_ai_merge.py`, and repairs the import in one step. No stash required.

---

## 3. Version map — 50 versions, 10 with no surviving spec

Confirmed independently by `deep_audit.py` and `status_complete.ps1`.

| Version | Commits | Spec file | Note |
|---|---|---|---|
| V23 | 2 | ❌ | AI warm-up content, send-queue fixes |
| V24 | 1 | ❌ | Stop leaking internal account label |
| **V26** | **5** | ❌ | **Group monitoring + Whisper voice transcription — 25 files carry its marker** |
| V31 | 1 | ❌ | Unify legacy mesh ask through AI generator |
| V34 | 1 | ❌ | Decouple TC reminder from mesh PAUSE |
| V36 | 3 | ❌ | Phone canonicalization + backfill |
| V37 | 2 | ❌ | Read-only LAN reports API + scoped CORS |
| V38 | 2 | ❌ | 24h post-reconnect rest for TC senders |
| V51 | 1 | ❌ | Auto-analyze story backlog |
| V52 | 1 | ❌ | The commit created during this session |

**V26 is the most serious** — a five-part subsystem including Whisper voice transcription,
with no document describing what it was scoped to deliver.

V32 and V46 have neither spec nor commits; those numbers were simply skipped.

### Prompt corpus

- 42 `V*.md` / `V*.txt` files, 773,671 bytes; 55 prompt files total in the audit corpus
- **18 specs were never committed to git** — V39 through V50 exist only on this machine
- `New Text Document (2).txt` is **byte-identical** to `V14_MASTER_PROMPT.md`
  (SHA256 `4a20e02ab01269ce`, 77,914 bytes) — a scratch copy inflating the corpus

Commit-subject tagging (`V<n> PART <k>:`) only begins at **V16**. Prompts numbered below
that are marked UNVERIFIABLE in `audit.md`, not "not done" — early work was committed under
free-form subjects (`v2.0`, `feat: ...`) and cannot be matched by tag.

---

## 4. Code health

| Check | Result |
|---|---|
| Unimplemented functions in production code | **0** |
| Unimplemented functions in tests | 108 — all mock/stub doubles, benign |
| Imports resolving to nothing | **1** — the `product_ai_merge` dangling import (§2) |
| Byte-identical duplicate source files | 0 |
| Orphan source files | 21 |
| TODO / FIXME / XXX / HACK | see `audit.md` |

### Latent bug not covered by any test

`product_reports.py` — `product_mentioners_rows`, the «مشاهده فروشندگان اخیر» seller
drill-down, dropped its SQL filter:

```python
-        .where(ProductMentionLog.product_name == product_name)
-        .limit(limit)
+        .limit(max(2000, min(output_limit * 25, 5000)))
```

It now pulls up to 5000 newest rows **across all products** and filters in Python. A
rarely-mentioned product whose mentions fall outside that window will show **zero sellers**
despite matching rows existing.

### Uncommitted AI-merge feature — gating defect

`product_reports.py` changed the grouping key **unconditionally**:

```python
key = product_canonical_key(r.product_name) or product_group_key(r.product_name)
```

This is not inside any `if ai_merge:`. Only the second pass is gated, so the default
reporting path changed for every caller even at `ai_merge=False`. The code comment claimed
"deterministic grouping remains the default and fallback" — it did not.

**Fixed 2026-07-31** — gated behind `if ai_merge:`; the default now reproduces V44 exactly.

> **Correction.** An earlier revision of this document stated that this defect "is what
> breaks the V45 and V49 tests". That was wrong. Those two tests were checked out at
> `5f7d944` (`origin/main`, before any AI-merge work existed) and **fail there identically**
> — `assert (None is not None)` and `assert 3 == 2`. They are pre-existing failures,
> unrelated to this feature. See §5.

---

## 5. Test baseline — VALIDATED on `afrapayam-redesign`

Re-run after the branch restore, inside `claudegreenapi-backend-1`:

```
6 failed, 1397 passed, 8 warnings in 21.45s     (1403 collected)
```

After the §4 gating fix plus a test-double repair, the suite stands at:

```
3 failed, 1400 passed, 8 warnings in 23.56s
```

### Failure attribution — established by experiment, not inference

`5f7d944` (`origin/main`) was checked out and the two suspect tests re-run against it:

| Test | On `origin/main` | Verdict |
|---|---|---|
| `test_v45_part2.py::test_report_filters_preexisting_own_number_rows` | **FAILS** — `assert (None is not None)` | **Pre-existing**, unrelated |
| `test_v49_part4.py::test_v49_detection_report_exclusion_and_retention_end_to_end` | **FAILS** — `assert 3 == 2` | **Pre-existing**, unrelated |

Both hit the **real database** with `limit=1000`, making them sensitive to live data volume
and to wall-clock date. They almost certainly rotted between 2026-07-26 and today rather
than being broken by a code change.

**Consequence: `origin/main` is not green.** The V51 PART 1 commit message claims
"1387 → 1394, zero regressions", but that commit fails these 2 tests when run on
2026-07-31. The 1394 figure is not reproducible today.

### Current attribution

| Failure | Cause |
|---|---|
| `test_v43_part3_e2e.py` ×4 | AI-merge work — **FIXED** (test double now tracks the real signature) |
| `test_v45_part2.py` | Pre-existing on `origin/main` |
| `test_v49_part4.py` | Pre-existing on `origin/main` |
| `test_v44_part2_grouping_fix.py::test_bosch_dishwasher_shorthand...` | **The gating fix itself.** This test calls `top_products_rows(db, days=7, limit=150)` with no `ai_merge` and expects `mention_count == 13`, i.e. it requires the canonical key ON by default — contradicting the gating decision |

Realistic target: **2 failed / 1401 passed**, once the V44 test is updated to opt in with
`ai_merge=True`. The 2 remaining are pre-existing and should be triaged separately.

All V50 and V51 tests passed. All 6 failures came from the uncommitted AI-merge work:

| Failure | Cause |
|---|---|
| `test_v43_part3_e2e.py::test_rolling_window_max_limit_with_each_source[None\|pv\|group\|status]` | `_spy()` test double rejects the new `ai_merge` kwarg — 4 failures, trivial fix |
| `test_v45_part2.py:245` | Grouping change — product no longer found by exact name |
| `test_v49_part4.py:92` | Grouping change — `assert 3 == 2`, one extra row merged |

Reference: `origin/main` should be **1394 passing** (per the V51 PART 1 commit message). The
+9 collected here are the uncommitted `test_v44_part2_grouping_fix.py` additions plus
`test_product_ai_merge.py`.

---

## 6. Runtime — healthy

| Service | State |
|---|---|
| `claudegreenapi-backend-1` | Up 16h, `/docs` → HTTP 200 |
| `claudegreenapi-worker-general-1` | Up 16h, executing tasks |
| `claudegreenapi-beat-1` | Up 16h, dispatching on schedule |
| `claudegreenapi-db-1` / `-redis-1` | Up 16h |
| `claudegreenapi-frontend-1` | Up 16h — ⚠ see below |

### V50 scheduled story fetch — verified live

```
04:14:20  received → succeeded in 11.80s
04:44:20  received → succeeded in 14.21s
05:14:20  received → succeeded in 12.24s
```

392 log entries, exactly on the 1800s cadence. Backend/worker code is volume-mounted
(`./backend:/app`), so commits take effect without a rebuild.

### Frontend is serving a stale build

The frontend container has **no volume mount** (`Mounts: []`) — code is baked into the
image.

| | |
|---|---|
| Image built | 2026-07-29 16:13 UTC |
| Rebrand commit `74a6074` | 2026-07-30 12:00 UTC |

Port 3002 serves a build ~20 hours older than the rebrand. Requires
`docker compose up -d --build frontend` **after** the branch is restored.

---

## 7. Configuration

`.env` — 19 keys set. Two `.env.example` keys are absent:

| Key | Fallback | Risk |
|---|---|---|
| `AUTO_FAILOVER_ON_YELLOW_CARD` | `False` | None — safe default |
| `REPORTS_ALLOWED_ORIGINS` | Hardcoded `192.168.170.8:3100,192.168.170.10:3100` in `config.py:51` | Moving the LAN machine needs a **code change**, which the comment says it should not |

**AI provider pool is degraded to one provider.** `GEMINI_API_KEY` and `DEEPSEEK_API_KEY`
are both empty; only `OPENAI_API_KEY` is set. V42's self-healing model discovery has no
alternate provider to fail over to.

### Correction to an earlier finding

`config.py`'s `extra = "ignore"` was initially reported as a critical boot-crash fix. **It is
not.** Verified directly: `main` has no `extra` line, `ENVIRONMENT` remains in `.env`, and
`from app.config import settings` returns `SETTINGS OK` with the API answering HTTP 200. It
is a hygiene improvement only.

---

## 8. Repository hygiene

- ~40 `V*_MASTER_PROMPT.md` files at repo root, no archive directory
- Junk tracked at root: `New Text Document.txt` (26 KB), `New Text Document (2).txt` (77 KB,
  duplicate of V14), `New Microsoft Visio Drawing.vsdx` (**0 bytes**),
  `project_structure.txt` (**1.1 MB**), and three 7-byte files named `qc`, `query`, `start`
- 7 untracked one-off diagnostics (`backend/scripts/diag_*_20260729.py`)
- `analyze_project.py` + `prompt_analysis.txt` + `analysis_report.md` — an **abandoned
  prototype**. It cannot run: it requires `DEEPSEEK_API_KEY`, which is empty
- Git warns `LF will be replaced by CRLF` on every backend file despite `.gitattributes`

---

## 9. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| 1 | ~~Restore `afrapayam-redesign`~~ | ✅ **DONE** — verified collision-free, import repaired |
| 2 | ~~Re-run the test suite~~ | ✅ **DONE** — 6 failed / 1397 passed, baseline now valid |
| 3 | Fix the AI-merge gating defect | **Next up.** Move the canonical-key swap inside `if ai_merge:` so the default path is byte-identical to V44. Expected to clear the V45 + V49 failures; the 4 spy failures then need `ai_merge=False` added to the `_spy()` signature |
| 4 | Rebuild the frontend image | After #1, or the rebrand stays invisible |
| 5 | Reconstruct specs for V26 and the other 9 | V26 first — 5 commits, 25 files, zero documentation |
| 6 | Commit the 18 untracked specs | Low effort, prevents further loss |
| 7 | Push `afrapayam-redesign` | Nothing since V51 exists anywhere but this machine |

---

*Generated 2026-07-31. Regenerate the per-prompt detail with:*
`python deep_audit.py --output audit.md`
