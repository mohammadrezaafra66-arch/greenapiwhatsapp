// V63 — helpers for the campaign's hand-picked product pool.
//
// Without a pool, every recipient gets the same products: the first `product_count` rows the
// catalogue happens to return (price_service.get_products has no ORDER BY). The pool lets the
// operator say "advertise THESE fifteen", and the backend draws each recipient's share from it.
//
// Pure functions so the selection arithmetic and the Persian wording are unit-tested and cannot
// drift; the page stays a thin renderer.

/** Products out of GET /reporting/products-table, whatever shape it arrives in. */
export function extractProducts(response) {
  if (Array.isArray(response)) return response;
  if (response && Array.isArray(response.items)) return response.items;
  return [];
}

/** Total matches the API reports, falling back to what we can see. */
export function totalProducts(response) {
  if (response && typeof response.total === "number") return response.total;
  return extractProducts(response).length;
}

/** Brand list for the filter dropdown. */
export function brandOptions(response) {
  return (response && Array.isArray(response.brands)) ? response.brands : [];
}

/** Toggle one product id in the pool, returning a NEW array (React state must not mutate). */
export function togglePooled(pool, id) {
  const key = String(id);
  const cur = (pool || []).map(String);
  return cur.includes(key) ? cur.filter((x) => x !== key) : [...cur, key];
}

export function isPooled(pool, id) {
  return (pool || []).map(String).includes(String(id));
}

/** «۸۲,۴۰۰,۰۰۰ تومان» — or a plain marker when the catalogue has no price for it. */
export function priceLabel(product) {
  if (!product) return "";
  if (product.price_formatted) return `${product.price_formatted} تومان`;
  const n = Number(product.price);
  return Number.isFinite(n) && n > 0 ? `${n.toLocaleString("en-US")} تومان` : "بدون قیمت";
}

/**
 * The sentence under the picker. It has to answer the question the operator actually has:
 * "what will my recipients see?" — not just how many boxes are ticked.
 */
export function poolSummary(pool, perMessage) {
  const n = (pool || []).length;
  if (n === 0) {
    return "هیچ محصولی انتخاب نشده — مثل قبل، محصولات پیش‌فرض به همه‌ی مخاطبان می‌رود.";
  }
  const per = Math.max(1, Number(perMessage) || 1);
  if (n <= per) {
    return `${n} محصول انتخاب شده. چون «تعداد محصول در هر پیام» ${per} است، `
      + `همه‌ی ${n} محصول به هر مخاطب می‌رود و تنوعی ایجاد نمی‌شود.`;
  }
  return `${n} محصول انتخاب شده. به هر مخاطب ${per} محصول تصادفی از این فهرست می‌رود — `
    + `هر مخاطب ترکیب متفاوتی می‌بیند، ولی همان مخاطب همیشه همان محصولات را می‌بیند.`;
}

/**
 * Warning when the pool cannot actually produce variety. Ticking 3 products and asking for 3 per
 * message is a silent no-op: everyone still sees an identical message, which is the exact thing
 * the pool exists to avoid.
 */
export function poolVarietyWarning(pool, perMessage) {
  const n = (pool || []).length;
  const per = Math.max(1, Number(perMessage) || 1);
  if (n === 0) return "";
  if (n <= per) {
    return `برای اینکه مخاطبان پیام‌های متفاوت ببینند، تعداد محصولات انتخابی باید از `
      + `${per} بیشتر باشد. الان ${n} محصول انتخاب شده.`;
  }
  return "";
}
