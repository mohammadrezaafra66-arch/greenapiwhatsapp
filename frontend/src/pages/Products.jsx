import React from "react";
import { ProductsApi as Api, ReportingApi } from "../api.js";
import { Spinner, Empty } from "../ui.jsx";

export default function Products() {
  const [data, setData] = React.useState(null); // brand-grouped array
  const [mentions, setMentions] = React.useState([]);
  const [supa, setSupa] = React.useState(null); // V16 PART 1 — connectivity state
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [search, setSearch] = React.useState("");
  const [expandedBrands, setExpandedBrands] = React.useState({});
  const firstLoadRef = React.useRef(true);

  const load = React.useCallback(async () => {
    try {
      const [p, m, s] = await Promise.all([
        Api.list(),
        ReportingApi.productMentions(),
        Api.supabaseStatus().catch(() => null),
      ]);
      const groups = p || [];
      setData(groups);
      setMentions(m || []);
      setSupa(s);
      setError(null);
      // Auto-expand the first brand after the initial load.
      if (firstLoadRef.current && groups.length > 0) {
        firstLoadRef.current = false;
        setExpandedBrands((prev) =>
          prev && Object.keys(prev).length > 0 ? prev : { [groups[0].brand]: true }
        );
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const toggleBrand = (brand) =>
    setExpandedBrands((prev) => ({ ...prev, [brand]: !prev[brand] }));

  // V16 PART 2 — full catalog table (server-paginated, mirrors the contacts pattern)
  const [showTable, setShowTable] = React.useState(false);
  const [table, setTable] = React.useState(null);
  const [tBrand, setTBrand] = React.useState("");
  const [tSkip, setTSkip] = React.useState(0);
  const T_LIMIT = 20;
  const loadTable = React.useCallback(async () => {
    try {
      const params = { skip: tSkip, limit: T_LIMIT };
      if (tBrand) params.brands = tBrand;
      if (search.trim()) params.search = search.trim();
      setTable(await Api.table(params));
    } catch (e) {
      setTable({ items: [], total: 0, brands: [], error: e?.message });
    }
  }, [tBrand, tSkip, search]);
  React.useEffect(() => { if (showTable) loadTable(); }, [showTable, loadTable]);
  React.useEffect(() => { setTSkip(0); }, [tBrand, search]);

  const totalProducts = React.useMemo(() => {
    if (!data) return 0;
    return data.reduce((sum, g) => sum + (g.product_count || 0), 0);
  }, [data]);

  // Map product name -> first mentioner (for the badge)
  const mentionByName = React.useMemo(() => {
    const map = {};
    for (const m of mentions) {
      if (m.product && !(m.product in map)) map[m.product] = m.sender_name || m.sender || "";
    }
    return map;
  }, [mentions]);

  const filtered = React.useMemo(() => {
    if (!data) return [];
    const term = search.trim().toLowerCase();
    if (!term) return data;
    return data
      .map((g) => ({
        ...g,
        products: (g.products || []).filter((p) => {
          const name = (p.name || "").toLowerCase();
          const model = (p.model || "").toLowerCase();
          return name.includes(term) || model.includes(term);
        }),
      }))
      .filter((g) => (g.products || []).length > 0);
  }, [data, search]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold">محصولات افراکالا</h2>
        <div className="flex gap-2 flex-wrap items-center">
          {/* V16 PART 2 — browse without searching: brand-grouped dropdown */}
          {data && data.length > 0 && (
            <select
              className="input w-auto max-w-xs"
              value=""
              onChange={(e) => { if (e.target.value) setSearch(e.target.value); }}
              title="انتخاب محصول از فهرست (بدون جستجو)"
            >
              <option value="">— انتخاب محصول از فهرست —</option>
              {data.map((g) => (
                <optgroup key={g.brand} label={g.brand}>
                  {(g.products || []).map((p, i) => (
                    <option key={p.id ?? `${g.brand}-${i}`} value={p.name}>{p.name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          )}
          <input
            className="input max-w-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="جستجو در محصولات..."
          />
        </div>
      </div>

      {data && (
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="text-sm text-slate-400">
            {totalProducts} محصول در {data.length} برند | مرتب‌شده از ارزان به گران
          </div>
          <button className="btn-secondary text-xs" onClick={() => setShowTable((v) => !v)}>
            {showTable ? "نمایش گروه‌بندی برند" : "📋 نمایش جدول کامل کاتالوگ"}
          </button>
        </div>
      )}

      {/* V16 PART 2 — full catalog table with brand filter + pagination */}
      {showTable && data && data.length > 0 && (
        <div className="card space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <select className="input w-auto" value={tBrand} onChange={(e) => setTBrand(e.target.value)}>
              <option value="">همه برندها</option>
              {(table?.brands || []).map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
            <span className="text-xs text-slate-400">{table?.total ?? 0} محصول</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="text-right p-2">برند</th>
                  <th className="text-right p-2">نام/مدل</th>
                  <th className="text-right p-2">قیمت (تومان)</th>
                </tr>
              </thead>
              <tbody>
                {(table?.items || []).map((p, i) => (
                  <tr key={p.id ?? i} className="border-b border-slate-800">
                    <td className="p-2 text-slate-300">{p.brand}</td>
                    <td className="p-2 font-bold">{p.name}{p.model ? ` — ${p.model}` : ""}</td>
                    <td className="p-2">{p.price_formatted ? <span className="text-emerald-400">{p.price_formatted}</span> : <span className="text-slate-500">—</span>}</td>
                  </tr>
                ))}
                {table && (table.items || []).length === 0 && (
                  <tr><td colSpan={3} className="p-3 text-center text-slate-500">موردی یافت نشد</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {table && table.total > T_LIMIT && (
            <div className="flex items-center justify-between text-xs">
              <button className="btn-secondary text-xs" disabled={tSkip === 0} onClick={() => setTSkip(Math.max(0, tSkip - T_LIMIT))}>‹ قبلی</button>
              <span className="text-slate-400">صفحه {Math.floor(tSkip / T_LIMIT) + 1} از {Math.max(1, Math.ceil(table.total / T_LIMIT))}</span>
              <button className="btn-secondary text-xs" disabled={tSkip + T_LIMIT >= table.total} onClick={() => setTSkip(tSkip + T_LIMIT)}>بعدی ›</button>
            </div>
          )}
        </div>
      )}

      {/* V16 PART 1 — three distinct states: loading / disconnected / connected-but-empty */}
      {loading && !data && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {supa && supa.status === "disconnected" && (
        <div className="card border-amber-500/50 bg-amber-500/10 text-amber-200 text-sm">
          ⚠️ اتصال به Supabase برقرار نیست — لپ‌تاپ Supabase (۱۹۲.۱۶۸.۱۷۰.۱۰) را روشن کنید یا آدرس آن را بررسی کنید.
          <div className="text-xs text-amber-300/80 mt-1">{supa?.rest_products?.detail || supa?.tcp?.detail || ""}</div>
        </div>
      )}
      {data && data.length === 0 && !loading && (!supa || supa.status !== "disconnected") && (
        <Empty label="محصولی یافت نشد" />
      )}
      {data && data.length > 0 && filtered.length === 0 && (
        <Empty label="محصولی یافت نشد" />
      )}

      {filtered.length > 0 && (
        <div className="space-y-3">
          {filtered.map((g) => {
            const open = !!expandedBrands[g.brand];
            return (
              <div key={g.brand} className="space-y-2">
                <button
                  type="button"
                  onClick={() => toggleBrand(g.brand)}
                  className="w-full flex items-center justify-between bg-slate-800 rounded-lg p-3 hover:bg-slate-700 transition-colors text-right"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400">{open ? "▼" : "◀"}</span>
                    <span className="font-bold">{g.brand}</span>
                  </div>
                  <span className="badge bg-slate-700 text-slate-300 border-slate-600">
                    {g.product_count} محصول
                  </span>
                </button>

                {open && (
                  <div className="card overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-slate-400 border-b border-slate-700">
                          <th className="text-right p-2">نام محصول</th>
                          <th className="text-right p-2">مدل</th>
                          <th className="text-right p-2">ظرفیت</th>
                          <th className="text-right p-2">قیمت (تومان)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(g.products || []).map((p, i) => {
                          const mentioned = p.name in mentionByName;
                          const by = mentionByName[p.name];
                          return (
                            <tr key={p.id ?? `${g.brand}-${i}`} className="border-b border-slate-800">
                              <td className="p-2 font-bold">
                                {p.name}
                                {mentioned && (
                                  <span className="badge mr-2 bg-amber-500/20 text-amber-300 border-amber-500/40">
                                    ذکر شده{by ? ` · ${by}` : ""}
                                  </span>
                                )}
                              </td>
                              <td className="p-2 text-slate-300">{p.model || "—"}</td>
                              <td className="p-2 text-slate-300">{p.capacity || "—"}</td>
                              <td className="p-2">
                                {p.price_formatted ? (
                                  <span className="text-emerald-400">{p.price_formatted}</span>
                                ) : (
                                  <span className="text-slate-500">تماس بگیرید</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
