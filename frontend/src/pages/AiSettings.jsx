import React from "react";
import { AiApi } from "../api.js";
import { Spinner } from "../ui.jsx";

const fa = (n) => Number(n ?? 0).toLocaleString("fa-IR");

const PROVIDERS = [
  { key: "openai", emoji: "🤖", name: "OpenAI GPT-4o-mini", priority: 1 },
  { key: "deepseek", emoji: "🔵", name: "DeepSeek Chat", priority: 2 },
  { key: "gemini", emoji: "💎", name: "Google Gemini 2.0 Flash", priority: 3 },
];

export default function AiSettings() {
  const [providers, setProviders] = React.useState(null);
  const [stats, setStats] = React.useState([]);
  const [err, setErr] = React.useState(null);

  const load = React.useCallback(async () => {
    try {
      const [p, s] = await Promise.all([AiApi.providers(), AiApi.stats()]);
      setProviders(p);
      setStats(Array.isArray(s) ? s : []);
      setErr(null);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    }
  }, []);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const statOf = (key) => stats.find((s) => s.provider === key) || { calls: 0, total_tokens: 0, errors: 0 };

  if (!providers && !err) return <Spinner />;

  return (
    <div className="space-y-5">
      <h2 className="text-2xl font-bold">تنظیمات هوش مصنوعی</h2>

      {err && <div className="card bg-red-50 text-red-700 border-red-200">{err}</div>}

      <div className="card bg-canvas text-sm text-muted space-y-1">
        <p>🔒 کلیدها در سرور تنظیم می‌شوند (<code>.env</code>) — به دلایل امنیتی اینجا قابل ویرایش نیستند.</p>
        <p>سیستم به ترتیب اولویت امتحان می‌کند. اولین پاسخ موفق استفاده می‌شود.</p>
      </div>

      {/* Provider cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PROVIDERS.map((p) => {
          const on = providers?.[p.key];
          return (
            <div key={p.key} className="card space-y-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 font-bold">
                  <span className="text-2xl">{p.emoji}</span>
                  {p.name}
                </span>
                <span className="badge bg-slate-100 text-slate-600 border-slate-300">اولویت {fa(p.priority)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span
                  className={`badge ${on ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`}
                >
                  <span className={`inline-block w-2 h-2 rounded-full ml-1 align-middle ${on ? "bg-brand animate-pulse" : "bg-slate-400"}`} />
                  {on ? "فعال" : "غیرفعال"}
                </span>
                <span className="text-xs text-muted">
                  {fa(statOf(p.key).calls)} استفاده · {fa(statOf(p.key).total_tokens)} توکن
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Live stats table */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold">آمار زنده مصرف (۲۴ ساعت اخیر)</h3>
          <span className="text-xs text-muted">به‌روزرسانی هر ۳۰ ثانیه</span>
        </div>
        <div className="table-wrap">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
                <th className="text-right p-2">ارائه‌دهنده</th>
                <th className="text-right p-2">تعداد استفاده</th>
                <th className="text-right p-2">توکن مصرفی</th>
                <th className="text-right p-2">خطاها</th>
              </tr>
            </thead>
            <tbody>
              {PROVIDERS.map((p) => {
                const s = statOf(p.key);
                return (
                  <tr key={p.key} className="border-b border-line">
                    <td className="p-2">{p.emoji} {p.name}</td>
                    <td className="p-2 font-bold">{fa(s.calls)}</td>
                    <td className="p-2 text-sky-700">{fa(s.total_tokens)}</td>
                    <td className={`p-2 ${s.errors > 0 ? "text-red-700" : "text-muted"}`}>{fa(s.errors)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
