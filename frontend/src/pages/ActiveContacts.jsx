import React from "react";
import { ActiveContactsApi } from "../api.js";
import { toast } from "../ui/toast.jsx";

// V45 PART 3 — «مخاطبین فعال واتساپ»: every distinct number seen active (story / group / channel /
// broadcast), deduped, for lead generation. Our own numbers are never harvested here.
export default function ActiveContacts() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [search, setSearch] = React.useState("");

  const load = async (q = "") => {
    setLoading(true);
    try {
      setData(await ActiveContactsApi.list(q ? { search: q } : {}));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    load();
  }, []);

  const items = data?.items || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-bold">مخاطبین فعال واتساپ</h2>
          <p className="text-sm text-slate-400 mt-1">
            شماره‌هایی که در استوری‌ها، گروه‌ها، کانال‌ها یا لیست‌های انتشار فعال دیده شده‌اند
            (بدون تکرار){data?.count != null ? ` · ${Number(data.count).toLocaleString("fa-IR")} مورد` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a className="btn-secondary text-sm" href={ActiveContactsApi.exportUrl()} target="_blank" rel="noreferrer">
            ⬇️ خروجی اکسل
          </a>
          <button className="btn-secondary text-sm" disabled={loading} onClick={() => load(search)}>
            {loading ? "..." : "🔄 تازه‌سازی"}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input className="input" value={search} onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load(search)}
          placeholder="جستجوی شماره یا نام…" />
        <button className="btn-primary" onClick={() => load(search)}>جستجو</button>
      </div>

      <div className="card overflow-x-auto">
        {items.length === 0 ? (
          <p className="text-slate-500 text-sm">هنوز مخاطب فعالی ثبت نشده است.</p>
        ) : (
          <table className="w-full text-sm text-right">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="py-2 px-2">#</th>
                <th className="py-2 px-2">شماره</th>
                <th className="py-2 px-2">نام</th>
                <th className="py-2 px-2">اولین منبع</th>
                <th className="py-2 px-2">اولین مشاهده</th>
                <th className="py-2 px-2">آخرین مشاهده</th>
                <th className="py-2 px-2">دفعات</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r, i) => (
                <tr key={r.id} className="border-b border-slate-800">
                  <td className="py-2 px-2 text-slate-500">{Number(i + 1).toLocaleString("fa-IR")}</td>
                  <td className="py-2 px-2 font-mono">{r.phone}</td>
                  <td className="py-2 px-2 text-slate-300">{r.name || "—"}</td>
                  <td className="py-2 px-2">
                    <span className="badge text-xs bg-slate-500/20 text-slate-300 border-slate-500/40">
                      {r.source_label}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-slate-400 text-xs whitespace-nowrap">{r.first_seen_shamsi || "—"}</td>
                  <td className="py-2 px-2 text-slate-400 text-xs whitespace-nowrap">{r.last_seen_shamsi || "—"}</td>
                  <td className="py-2 px-2 text-slate-300">{Number(r.sighting_count || 0).toLocaleString("fa-IR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
