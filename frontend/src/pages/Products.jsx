import React from "react";
import { ProductsApi as Api, ReportingApi } from "../api.js";
import { Spinner, Empty } from "../ui.jsx";

function priceFmt(price) {
  if (price === null || price === undefined || price === "") return "تماس بگیرید";
  const n = Number(price);
  if (Number.isNaN(n)) return "تماس بگیرید";
  return n.toLocaleString("fa-IR") + " تومان";
}

export default function Products() {
  const [products, setProducts] = React.useState(null);
  const [mentions, setMentions] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [q, setQ] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      const [p, m] = await Promise.all([Api.list(), ReportingApi.productMentions()]);
      setProducts(p || []);
      setMentions(m || []);
      setError(null);
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

  // Map product name -> first mentioner (for the badge)
  const mentionByName = React.useMemo(() => {
    const map = {};
    for (const m of mentions) {
      if (m.product && !(m.product in map)) map[m.product] = m.sender_name || m.sender || "";
    }
    return map;
  }, [mentions]);

  const filtered = React.useMemo(() => {
    if (!products) return [];
    const term = q.trim().toLowerCase();
    if (!term) return products;
    return products.filter((p) => (p.name || "").toLowerCase().includes(term));
  }, [products, q]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold">رصد محصولات</h2>
        <button className="btn-secondary" onClick={load}>بروزرسانی</button>
      </div>

      <div className="card">
        <label className="label">جستجو بر اساس نام</label>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="نام محصول را بنویسید..." />
      </div>

      {loading && !products && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {products && filtered.length === 0 && !loading && <Empty label="محصولی یافت نشد." />}

      {filtered.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">نام</th>
                <th className="text-right p-2">قیمت</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p, i) => {
                const mentioned = p.name in mentionByName;
                const by = mentionByName[p.name];
                return (
                  <tr key={p.name || i} className="border-b border-slate-800">
                    <td className="p-2 font-bold">{p.name}</td>
                    <td className="p-2 text-slate-300">{priceFmt(p.price)}</td>
                    <td className="p-2">
                      {mentioned && (
                        <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">
                          ذکر شده در گروه{by ? ` · ${by}` : ""}
                        </span>
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
}
