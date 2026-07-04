import React from "react";
import { ProductsApi as Api, ReportingApi } from "../api.js";
import { Spinner, Empty } from "../ui.jsx";

export default function Products() {
  const [data, setData] = React.useState(null); // brand-grouped array
  const [mentions, setMentions] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [search, setSearch] = React.useState("");
  const [expandedBrands, setExpandedBrands] = React.useState({});
  const firstLoadRef = React.useRef(true);

  const load = React.useCallback(async () => {
    try {
      const [p, m] = await Promise.all([Api.list(), ReportingApi.productMentions()]);
      const groups = p || [];
      setData(groups);
      setMentions(m || []);
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
        <input
          className="input max-w-xs"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="جستجو در محصولات..."
        />
      </div>

      {data && (
        <div className="text-sm text-slate-400">
          {totalProducts} محصول در {data.length} برند | مرتب‌شده از ارزان به گران
        </div>
      )}

      {loading && !data && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && !loading && <Empty label="محصولی یافت نشد" />}
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
