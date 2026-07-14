"""Per-group product selection for campaigns — anti-Meta variation + weighted picks.

Pure functions (no DB/network) so the selection logic is unit-testable. A product is
a dict with at least a 'name' (and optionally 'id'); weights key off name or id."""
import random


def _weight_key(p: dict) -> str:
    return str(p.get("name") or p.get("id") or "")


def weighted_sample(products: list, weights: dict, k: int) -> list:
    """Pick k distinct products using weights (higher weight = more likely).
    Missing/invalid weights default to 1. Never returns duplicates."""
    pool = list(products)
    weights = weights or {}
    chosen = []
    k = min(k, len(pool))
    for _ in range(k):
        ws = []
        for p in pool:
            try:
                w = float(weights.get(_weight_key(p), 1))
            except (TypeError, ValueError):
                w = 1.0
            ws.append(max(0.01, w))
        pick = random.choices(pool, weights=ws, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen


def select_group_products(pool: list, mode: str, per_group: int,
                          weights: dict | None, group_index: int,
                          used: set | None = None, last_picks: list | None = None) -> list:
    """Choose the products to advertise to one group.

    mode:
      - same             → first `per_group` from the pool (identical for every group)
      - per_group_random → weighted-random `per_group` subset (differs per group)
      - rotate           → a rotating slice so consecutive groups get different products

    V15 Item 22 — cross-group dedup: pass a persistent `used` set (and the previous
    group's `last_picks`). Each group draws from the products NOT already used this run;
    when the pool is exhausted a new cycle starts, but the immediately-preceding group's
    picks stay excluded so two consecutive groups never get the identical set.
    """
    if not pool:
        return []
    per_group = max(1, per_group)
    n = len(pool)

    if mode in ("per_group_random", "rotate") and used is not None:
        remaining = [p for p in pool if _weight_key(p) not in used]
        if len(remaining) < per_group:
            # Pool exhausted → start a fresh cycle, but keep ONE of the previous group's
            # picks excluded so the next group can't repeat the exact same set.
            used.clear()
            if last_picks:
                used.add(_weight_key(last_picks[0]))
            remaining = [p for p in pool if _weight_key(p) not in used]
            if len(remaining) < per_group:      # per_group ≈ pool size — unavoidable reuse
                remaining = list(pool)
        if mode == "rotate":
            picks = remaining[:per_group]        # strict order, no repeats until cycled
        else:
            picks = weighted_sample(remaining, weights or {}, per_group)
        used.update(_weight_key(p) for p in picks)
        return picks

    # ── legacy stateless behavior (mode 'same', or no `used` set supplied) ──
    if mode == "per_group_random":
        return weighted_sample(pool, weights or {}, per_group)
    if mode == "rotate":
        start = (group_index * per_group) % n
        return [pool[(start + i) % n] for i in range(min(per_group, n))]
    # "same" (default)
    return pool[:per_group]
