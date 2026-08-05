# V67.1 Phase 7.2 — Shadow Operator Query Catalog (read-only)

Use time bounds. Prefer indexed columns. No Secrets. Avoid phone/PII columns.

## Latest snapshots (bounded)

```sql
SELECT id, account_id, observed_at, mismatch_class, severity, source
FROM fleet_shadow_snapshots
ORDER BY observed_at DESC
LIMIT 50;
```

## By account

```sql
SELECT observed_at, mismatch_class, severity, idempotency_key
FROM fleet_shadow_snapshots
WHERE account_id = :account_id
  AND observed_at >= :since
ORDER BY observed_at DESC
LIMIT 100;
```

## Mismatch / severity counts (window)

```sql
SELECT mismatch_class, COUNT(*)
FROM fleet_shadow_snapshots
WHERE observed_at >= :since
GROUP BY 1
ORDER BY 2 DESC;

SELECT severity, COUNT(*)
FROM fleet_shadow_snapshots
WHERE observed_at >= :since
GROUP BY 1;
```

## HIGH/CRITICAL

```sql
SELECT account_id, observed_at, mismatch_class, severity
FROM fleet_shadow_snapshots
WHERE severity IN ('HIGH','CRITICAL')
  AND observed_at >= :since
ORDER BY observed_at DESC
LIMIT 200;
```

## Stale / runtime unknown / permissive classes

```sql
SELECT mismatch_class, COUNT(*)
FROM fleet_shadow_snapshots
WHERE observed_at >= :since
  AND mismatch_class IN (
    'SENSOR_STALE','RUNTIME_UNKNOWN',
    'LEGACY_MORE_PERMISSIVE','V67_MORE_PERMISSIVE',
    'POLICY_VERSION_MISMATCH'
  )
GROUP BY 1;
```

## Idempotency / duplicates (should be zero collisions)

```sql
SELECT idempotency_key, COUNT(*)
FROM fleet_shadow_snapshots
GROUP BY 1
HAVING COUNT(*) > 1;
```

## Daily completeness

```sql
SELECT date_trunc('day', observed_at) AS day_utc, COUNT(*) AS rows,
       COUNT(DISTINCT account_id) AS accounts
FROM fleet_shadow_snapshots
WHERE observed_at >= :since
GROUP BY 1
ORDER BY 1;
```

## Coverage gap (requires cohort list CTE)

```sql
-- :cohort is a VALUES list or temp table of account_id
SELECT c.account_id
FROM (VALUES (:id1), (:id2)) AS c(account_id)
LEFT JOIN fleet_shadow_snapshots s
  ON s.account_id = c.account_id
 AND s.observed_at >= :day_start
 AND s.observed_at < :day_end
WHERE s.id IS NULL;
```

## Storage growth proxy

```sql
SELECT pg_size_pretty(pg_total_relation_size('fleet_shadow_snapshots'));
```
