"""V16 PART 2 — catalog browse helpers (flatten / filter / paginate).

Pure functions so the brand-grouping + pagination logic is unit-testable. Input is the
brand-grouped shape produced by /reporting/products:
  [{"brand": "...", "product_count": N, "products": [{id,name,model,capacity,price,...}]}]
"""


def flatten_catalog(brand_groups: list) -> list:
    """Flatten brand groups into one list of products (each carrying its brand),
    sorted cheapest→most-expensive (products without a price sort last)."""
    items = []
    for g in brand_groups or []:
        brand = g.get("brand", "سایر")
        for p in (g.get("products") or []):
            items.append({
                "id": p.get("id"),
                "brand": brand,
                "name": p.get("name", ""),
                "model": p.get("model", ""),
                "capacity": p.get("capacity", ""),
                "price": p.get("price"),
                "price_formatted": p.get("price_formatted"),
            })
    items.sort(key=lambda x: (x["price"] is None, x["price"] or 0))
    return items


def filter_catalog(items: list, brands: list | None = None, search: str | None = None) -> list:
    """Filter by a set of brand names and/or a case-insensitive name/model substring."""
    out = items
    if brands:
        wanted = {b.strip() for b in brands if b and b.strip()}
        if wanted:
            out = [it for it in out if it["brand"] in wanted]
    if search and search.strip():
        term = search.strip().lower()
        out = [it for it in out
               if term in (it["name"] or "").lower() or term in (it["model"] or "").lower()]
    return out


def paginate(items: list, skip: int = 0, limit: int = 20) -> dict:
    """Mirror the contacts-table pattern: {total, skip, limit, items}."""
    skip = max(0, skip)
    limit = max(1, min(limit, 500))
    total = len(items)
    return {"total": total, "skip": skip, "limit": limit, "items": items[skip:skip + limit]}


def brand_names(brand_groups: list) -> list:
    """Distinct brand names present in the catalog, sorted (for the filter dropdown)."""
    return sorted({g.get("brand", "سایر") for g in (brand_groups or [])})
