import React from "react";
import { CapabilitiesApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";

const fa = (n) => (n == null ? "—" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

function badge(supported) {
  if (supported === true) return <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">✅ پشتیبانی می‌شود</span>;
  if (supported === false) return <span className="badge bg-red-500/20 text-red-300 border-red-500/40">⛔ پشتیبانی نمی‌شود</span>;
  return <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40">❓ نامشخص</span>;
}

// PART G — the single source of truth for what the Green API plan can do.
export default function Capabilities() {
  const { data, loading, error } = useAsync(() => CapabilitiesApi.get(), []);
  if (loading) return <Spinner />;
  if (error) return <p className="text-red-400 text-sm">{error}</p>;

  const groups = data?.groups || {};
  const labels = data?.category_labels || {};
  const c = data?.counts || {};

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">قابلیت‌های Green API</h2>
      <p className="text-sm text-slate-400">
        این جدول نشان می‌دهد کدام قابلیت‌ها روی پلن فعلی شما فعال هستند. با «نامشخص» یعنی هنوز استفاده نشده و
        در اولین استفادهٔ واقعی یا بررسی هفتگی مشخص می‌شود.
      </p>

      <div className="flex flex-wrap gap-2 text-sm">
        <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">✅ {fa(c.supported)} فعال</span>
        <span className="badge bg-red-500/20 text-red-300 border-red-500/40">⛔ {fa(c.unsupported)} غیرفعال</span>
        <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40">❓ {fa(c.unknown)} نامشخص</span>
      </div>

      {Object.keys(groups).length === 0 ? <Empty label="هنوز قابلیتی ثبت نشده." /> : (
        Object.entries(groups).map(([cat, methods]) => (
          <div key={cat} className="card">
            <h3 className="font-bold mb-2">{labels[cat] || cat}</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-slate-400 text-xs">
                  <tr>
                    <th className="text-right p-2">متد</th>
                    <th className="text-right p-2">وضعیت</th>
                    <th className="text-right p-2">آخرین بررسی</th>
                    <th className="text-right p-2">توضیح</th>
                  </tr>
                </thead>
                <tbody>
                  {methods.map((m) => (
                    <tr key={m.method} className="border-t border-slate-800">
                      <td className="p-2 font-mono text-xs">{m.method}</td>
                      <td className="p-2">{badge(m.supported)}</td>
                      <td className="p-2 text-xs text-slate-500">{m.last_checked || "—"}</td>
                      <td className="p-2 text-xs text-slate-400">{m.note || (m.last_status_code ? `HTTP ${fa(m.last_status_code)}` : "—")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
