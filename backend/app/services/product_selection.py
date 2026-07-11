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
                          weights: dict | None, group_index: int) -> list:
    """Choose the products to advertise to one group.

    mode:
      - same             → first `per_group` from the pool (identical for every group)
      - per_group_random → weighted-random `per_group` subset (differs per group)
      - rotate           → a rotating slice so consecutive groups get different products
    """
    if not pool:
        return []
    per_group = max(1, per_group)
    n = len(pool)
    if mode == "per_group_random":
        return weighted_sample(pool, weights or {}, per_group)
    if mode == "rotate":
        start = (group_index * per_group) % n
        return [pool[(start + i) % n] for i in range(min(per_group, n))]
    # "same" (default)
    return pool[:per_group]
