import React from "react";
import { CapabilitiesApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";

const fa = (n) => (n == null ? "—" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

function badge(supported) {
  if (supported === true) return <span className="badge bg-brand-light text-brand border-brand/30">✅ پشتیبانی می‌شود</span>;
  if (supported === false) return <span className="badge bg-red-50 text-red-700 border-red-200">⛔ پشتیبانی نمی‌شود</span>;
  return <span className="badge bg-slate-100 text-slate-600 border-slate-300">❓ نامشخص</span>;
}

// PART G — the single source of truth for what the Green API plan can do.
export default function Capabilities() {
  const { data, loading, error } = useAsync(() => CapabilitiesApi.get(), []);
  if (loading) return <Spinner />;
  if (error) return <p className="text-red-700 text-sm">{error}</p>;

  const groups = data?.groups || {};
  const labels = data?.category_labels || {};
  const c = data?.counts || {};

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold text-ink">قابلیت‌های سرویس</h2>
      <p className="text-sm text-muted">
        این جدول نشان می‌دهد کدام قابلیت‌ها روی پلن فعلی شما فعال هستند. با «نامشخص» یعنی هنوز استفاده نشده و
        در اولین استفادهٔ واقعی یا بررسی هفتگی مشخص می‌شود.
      </p>

      <div className="flex flex-wrap gap-2 text-sm">
        <span className="badge bg-brand-light text-brand border-brand/30">✅ {fa(c.supported)} فعال</span>
        <span className="badge bg-red-50 text-red-700 border-red-200">⛔ {fa(c.unsupported)} غیرفعال</span>
        <span className="badge bg-slate-100 text-slate-600 border-slate-300">❓ {fa(c.unknown)} نامشخص</span>
      </div>

      {Object.keys(groups).length === 0 ? <Empty label="هنوز قابلیتی ثبت نشده." /> : (
        Object.entries(groups).map(([cat, methods]) => (
          <div key={cat} className="card">
            <h3 className="font-bold mb-2 text-ink">{labels[cat] || cat}</h3>
            <div className="table-wrap">
              <table className="w-full text-sm">
                <thead className="text-muted text-xs">
                  <tr>
                    <th className="text-right p-2">متد</th>
                    <th className="text-right p-2">وضعیت</th>
                    <th className="text-right p-2">آخرین بررسی</th>
                    <th className="text-right p-2">توضیح</th>
                  </tr>
                </thead>
                <tbody>
                  {methods.map((m) => (
                    <tr key={m.method} className="border-t border-line">
                      <td className="p-2 font-mono text-xs text-ink">{m.method}</td>
                      <td className="p-2">{badge(m.supported)}</td>
                      <td className="p-2 text-xs text-muted">{m.last_checked || "—"}</td>
                      <td className="p-2 text-xs text-muted">{m.note || (m.last_status_code ? `HTTP ${fa(m.last_status_code)}` : "—")}</td>
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
