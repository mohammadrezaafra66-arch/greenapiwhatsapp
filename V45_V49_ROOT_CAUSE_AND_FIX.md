# V45 & V49 — Root Cause and Fix

**Date:** 2026-07-31
**Result:** `main` is green — **1403 passed / 0 failed**, verified over three consecutive runs.

Both were **test defects**, not platform bugs. Neither was caused by V52. Both reproduce on
`5f7d944` (`origin/main`) where the V52 feature does not exist. But "pre-existing" described *when*
they broke, not *why* — this document covers the why, established by measurement.

---

## The shared defect

Both tests assert **exact counts** against `product_mention_logs` — a live, shared, continuously
growing table that neither test controls. `top_products_rows` clamps `limit` to 1000 and orders by
`mention_count DESC`, so what a test sees depends on how much unrelated traffic the platform logged
that day.

---

## V45 — `limit` truncation, decided by tie-break

### Measured

```
rows in the 2-day window   : 2,034
DISTINCT product_name      : 1,304
limit (clamped)            : 1,000
mention_count of the 1000th-ranked product : 1

products with mention_count >= 1 : 1,304
products with mention_count >= 2 :   237   <-- comfortably inside the top 1000
```

### Why it failed

The test inserted 2 rows: one from `OWN_PHONE`, one from `OUT_PHONE`.

- **Base query** (no exclusion) → `mention_count = 2`. Only 237 products reach 2, so it ranked
  safely. This assertion always passed.
- **Filtered query** (own number excluded) → `mention_count = 1`. Now it competed with ~1,067 other
  single-mention products for the leftover slots, and lost on an arbitrary tie-break.
  `assert f is not None` failed.

The exclusion logic the test exists to verify was never reached. The failure was arithmetic.

### Fix

Add a second `OUT_PHONE` row, so the count is **2 after exclusion** rather than 1:

```python
db.add(... sender_phone=OWN_PHONE ...)   # excluded by V45
db.add(... sender_phone=OUT_PHONE ...)   # counted
db.add(... sender_phone=OUT_PHONE ...)   # counted  <-- added
```

```python
assert b["mention_count"] == 3                                  # was 2
assert f["mention_count"] == 2 and f["sender_count"] == 1       # was 1 and 1
```

Both rows share `OUT_PHONE`, so `sender_count` stays 1 and the exclusion is still proven. A count of
2 puts the fixture among 238 products — far inside the 1000 cut.

---

## V49 — fixture name collides with production data

### Measured

```
rows matching the fixture product name in the 90-day window: 1
   instance_id = '7105325764'   ← the real Green API instance, not a test instance
```

### Why it failed

`pname` is not a literal — it comes from `detect_product_mentions(text, products)`, so it is a
**real product name that genuine traffic also advertises**. Cleanup is:

```python
delete(ProductMentionLog).where(ProductMentionLog.instance_id == TEST_INSTANCE)
```

which cannot touch the production row. That row merges into the same V44 group, so the expected
count of 2 arrives as 3.

The test could not be made hermetic by renaming: the name is produced by live detection, and
changing it would stop testing the detection path the test is named for.

### Fix

Measure the pre-existing contribution first, then assert on the **delta**:

```python
_rows = (await db.execute(
    _select(ProductMentionLog.product_name, ProductMentionLog.sender_phone)
    .where(ProductMentionLog.mentioned_at >= datetime.utcnow() - timedelta(days=90))
    .where(ProductMentionLog.instance_id != TEST_INSTANCE))).all()
baseline = sum(1 for _n, _p in _rows
               if _key(_n or "") == _target and OWN_CORE not in (_p or ""))
...
assert mine[0]["mention_count"] == baseline + 2
```

### One trap worth recording

The first attempt measured `baseline` **through `top_products_rows`** and got `0`, producing
`assert 3 == (0 + 2)`. Cause: the baseline query hits the *same* 1000-row truncation — a lone
production row has `mention_count = 1` and never survives the cut in a 90-day window holding 2,428
distinct products. It only became visible once the test's own rows pushed the group's count to 3.

The baseline therefore has to be counted **straight from the table**, bypassing the helper whose
truncation is the problem.

A second assertion after the purge needed the same treatment. The baseline rows sit inside the
90-day window, so they survive `purge_old_product_mentions` untouched.

---

## Verification

| Scope | Result |
|---|---|
| Both tests in isolation | 2 passed |
| Their full files | 9 passed |
| Full suite ×3 | **1403 passed / 0 failed** |

Run three times deliberately: these failures were tie-break dependent, so a single green run would
not have distinguished a fix from luck.

---

## What this changes about the baseline

| | |
|---|---|
| Before | 1401 passed / 2 failed — and the 2 could flip to passing on their own as data shifted |
| After | **1403 passed / 0 failed**, stable |

`main` can now be used as a deployment gate. Before this, a green run would not have meant the
suite was healthy — only that the day's data happened to cooperate.

---

## Rule for future tests

A test asserting an exact count against `product_mention_logs` must either:

1. use a fake DB (as `test_v44_part2_grouping_fix.py` does), or
2. own its data via a unique product name, or
3. measure a baseline from the table and assert the **delta**.

Asserting an absolute count assumes an empty table that these tests cannot create.
