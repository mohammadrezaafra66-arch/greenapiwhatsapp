import React from "react";
import { CallsApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";

const fa = (n) => (n == null ? "—" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

const STATUS_FA = { offer: "زنگ خورد", pickUp: "پاسخ داده شد", hangUp: "قطع شد", missed: "بی‌پاسخ", declined: "رد شد" };
const DIR_FA = { incoming: "ورودی ⬇️", outgoing: "خروجی ⬆️" };

// FEATURE 24 — call logs. Missed incoming = hot leads.
export default function Calls() {
  const [filter, setFilter] = React.useState({ direction: "", only_missed: false });
  const { data, loading, reload } = useAsync(
    () => CallsApi.list({
      ...(filter.direction ? { direction: filter.direction } : {}),
      ...(filter.only_missed ? { only_missed: true } : {}),
    }),
    [filter.direction, filter.only_missed]
  );

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">تماس‌ها</h2>
      <p className="text-sm text-slate-400">⭐ تماس‌های بی‌پاسخ ورودی، سرنخ‌های داغ هستند — با آنها تماس بگیرید یا پیام بدهید.</p>

      <div className="flex flex-wrap gap-2 items-center">
        <select className="input w-auto" value={filter.direction} onChange={(e) => setFilter({ ...filter, direction: e.target.value })}>
          <option value="">همه جهت‌ها</option>
          <option value="incoming">ورودی</option>
          <option value="outgoing">خروجی</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={filter.only_missed} onChange={(e) => setFilter({ ...filter, only_missed: e.target.checked })} />
          فقط بی‌پاسخ‌ها
        </label>
        <button className="btn-secondary text-xs" onClick={reload}>🔄 تازه‌سازی</button>
      </div>

      {loading ? <Spinner /> : (!data || data.length === 0) ? <Empty label="تماسی ثبت نشده." /> : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-slate-400 text-xs">
              <tr>
                <th className="text-right p-2">جهت</th>
                <th className="text-right p-2">شماره</th>
                <th className="text-right p-2">نام</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">زمان</th>
                <th className="text-right p-2">اقدام</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id} className={`border-t border-slate-800 ${c.is_hot_lead ? "bg-red-500/5" : ""}`}>
                  <td className="p-2">{DIR_FA[c.direction] || c.direction}</td>
                  <td className="p-2 font-mono text-xs">{c.from_phone || "—"}</td>
                  <td className="p-2">{c.contact_name || "—"}</td>
                  <td className={`p-2 ${c.is_hot_lead ? "text-red-300 font-bold" : ""}`}>{STATUS_FA[c.status] || c.status || "—"}{c.is_hot_lead && " 🔥"}</td>
                  <td className="p-2 text-xs text-slate-500">{c.called_at || "—"}</td>
                  <td className="p-2">
                    {c.from_phone && (
                      <div className="flex gap-1">
                        <a className="btn-secondary text-xs" href={`tel:${c.from_phone}`}>تماس بگیرید</a>
                        <a className="btn-secondary text-xs" href={`https://wa.me/${c.from_phone}`} target="_blank" rel="noreferrer">پیام بفرست</a>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
