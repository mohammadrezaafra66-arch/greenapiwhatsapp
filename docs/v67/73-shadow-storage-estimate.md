# V67.1 Phase 7.2 — Shadow Storage Estimate

## Evidence counts (ENV-A, read-only)

| Metric | Value |
|---|---|
| `accounts` | 26 |
| `fleet_accounts` | **0** (blocker for enrollment until seeded) |
| `fleet_shadow_snapshots` | 0 |
| Beat interval (code) | 300 s → **288 ticks/day** if both flags on |

## Formulas (conservative)

Let:

- `N` = number of cohort FleetAccounts observed per tick
- `F` = ticks/day = `86400 / schedule_seconds` (default 300 → 288)
- `R` = rows/day ≈ `N * F` (one snapshot per account per slot; idempotent retries do not duplicate)

Approximate row size (JSONB-heavy): **2–8 KiB** raw + index overhead ≈ **×1.5–2**.

Use **6 KiB effective/row** for planning.

### Parameterized table

| N | Rows/day | 14-day rows | ~Storage 14d |
|---|---|---|---|
| 3 | 864 | 12,096 | ~70–95 MiB |
| 10 | 2,880 | 40,320 | ~230–310 MiB |
| 25 (batch max default) | 7,200 | 100,800 | ~580–780 MiB |
| 26 (all accounts if enrolled) | 7,488 | 104,832 | ~600–820 MiB |

## Retention

No auto-delete authorized. Unresolved duration → D-SE-12.

## Query load

Indexes on `(account_id, observed_at DESC)`, mismatch, severity, HIGH/CRITICAL partial — suitable for bounded operator queries.

## Verdict

Storage is **not** a blocker for Stage A/B on ENV-A disk headroom.  
Enrollment (`fleet_accounts`) is the current structural blocker, not disk.
