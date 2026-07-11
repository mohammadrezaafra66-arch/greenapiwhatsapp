import React from "react";
import { AIKeysApi as Api } from "../api.js";
import { Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

const PROVIDERS = [
  { value: "openai", label: "OpenAI (GPT)" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "gemini", label: "Gemini" },
];

const PROVIDER_LABEL = { openai: "OpenAI (GPT)", deepseek: "DeepSeek", gemini: "Gemini" };
const PROVIDER_BADGE = {
  openai: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  deepseek: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  gemini: "bg-amber-500/20 text-amber-300 border-amber-500/40",
};

const STATUS_LABEL = {
  working: "سالم ✅",
  rate_limited: "به سقف رسیده ⏳",
  failed: "خطا ❌",
  invalid: "نامعتبر ⛔",
  unknown: "بررسی نشده ❓",
};
const STATUS_BADGE = {
  working: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  rate_limited: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  failed: "bg-red-500/20 text-red-300 border-red-500/40",
  invalid: "bg-red-600/20 text-red-300 border-red-600/40",
  unknown: "bg-slate-500/20 text-slate-300 border-slate-500/40",
};

export default function AiKeys() {
  const [keys, setKeys] = React.useState(null);
  const [pool, setPool] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [testingAll, setTestingAll] = React.useState(false);
  const [testingId, setTestingId] = React.useState("");

  // single add form
  const [provider, setProvider] = React.useState("openai");
  const [apiKey, setApiKey] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [showKey, setShowKey] = React.useState(false);
  const [adding, setAdding] = React.useState(false);

  // bulk add
  const [bulkProvider, setBulkProvider] = React.useState("openai");
  const [bulk, setBulk] = React.useState("");
  const [bulkAdding, setBulkAdding] = React.useState(false);

  const load = React.useCallback(async () => {
    setError("");
    try {
      const [k, p] = await Promise.all([Api.list(), Api.poolStatus()]);
      setKeys(Array.isArray(k) ? k : []);
      setPool(p || null);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setKeys([]);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 60000); // auto-refresh status every 60s
    return () => clearInterval(t);
  }, [load]);

  const addSingle = async () => {
    if (!apiKey.trim()) return toast.error("کلید API لازم است");
    setAdding(true);
    try {
      await Api.create({ provider, api_key: apiKey.trim(), label: label.trim() || null });
      setApiKey("");
      setLabel("");
      await load();
      toast.success("کلید افزوده شد");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setAdding(false);
    }
  };

  const addBulk = async () => {
    const arr = bulk
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((k) => ({ provider: bulkProvider, api_key: k, label: null }));
    if (arr.length === 0) return toast.error("هیچ کلیدی یافت نشد");
    setBulkAdding(true);
    try {
      const r = await Api.bulk(arr);
      setBulk("");
      await load();
      toast.success(`${fa(r?.added)} کلید افزوده شد`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBulkAdding(false);
    }
  };

  const testOne = async (id) => {
    setTestingId(id);
    try {
      const r = await Api.test(id);
      if (r?.status === "working") toast.success("کلید سالم است");
      else toast.error(`${STATUS_LABEL[r?.status] || r?.status}: ${r?.error || ""}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setTestingId("");
    }
  };

  const testAll = async () => {
    setTestingAll(true);
    try {
      const r = await Api.testAll();
      toast.info(
        `سالم: ${fa(r?.working)} | به سقف: ${fa(r?.rate_limited)} | نامعتبر: ${fa(r?.invalid)} | خطا: ${fa(r?.failed)}`
      );
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setTestingAll(false);
    }
  };

  const toggle = async (k) => {
    try {
      await Api.update(k.id, { is_active: !k.is_active });
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const editLabel = async (k) => {
    const next = window.prompt("برچسب جدید:", k.label || "");
    if (next === null) return;
    try {
      await Api.update(k.id, { label: next });
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const editKey = async (k) => {
    const next = window.prompt("کلید API جدید (خالی بگذارید تا تغییر نکند):", "");
    if (!next) return;
    try {
      await Api.update(k.id, { api_key: next.trim() });
      await load();
      toast.success("کلید به‌روزرسانی شد");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const remove = async (id) => {
    if (!(await confirmDialog("حذف این کلید؟"))) return;
    try {
      await Api.delete(id);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-2xl font-bold">کلیدهای هوش مصنوعی</h2>
        <button className="btn-secondary" disabled={testingAll} onClick={testAll}>
          {testingAll ? "در حال تست..." : "🧪 تست همه کلیدها"}
        </button>
      </div>

      <div className="card bg-sky-500/10 border-sky-500/30 text-sky-200 text-sm">
        سیستم به صورت خودکار از بین کلیدهای فعال و سالم به صورت رندوم استفاده می‌کند. کلیدهایی که به سقف
        رسیده‌اند موقتاً کنار گذاشته می‌شوند و بعد از مدتی دوباره امتحان می‌شوند.
      </div>

      {/* Pool summary */}
      {pool && (
        <div className="grid gap-3 sm:grid-cols-3">
          {PROVIDERS.map((p) => {
            const s = pool.by_provider?.[p.value] || { total: 0, active: 0, working: 0 };
            return (
              <div key={p.value} className="card space-y-2">
                <span className={`badge ${PROVIDER_BADGE[p.value]}`}>{p.label}</span>
                <div className="flex gap-4 text-sm text-slate-300">
                  <span>کل: {fa(s.total)}</span>
                  <span>فعال: {fa(s.active)}</span>
                  <span className="text-emerald-300">سالم: {fa(s.working)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add single */}
      <div className="card space-y-3">
        <h3 className="font-bold text-sm">افزودن کلید</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label">ارائه‌دهنده</label>
            <select className="input" value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">برچسب (اختیاری)</label>
            <input className="input" placeholder="مثلاً کلید اصلی GPT" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label">کلید API</label>
          <div className="flex gap-2">
            <input
              className="input flex-1"
              dir="ltr"
              type={showKey ? "text" : "password"}
              placeholder="sk-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button className="btn-secondary whitespace-nowrap" type="button" onClick={() => setShowKey((s) => !s)}>
              {showKey ? "پنهان" : "نمایش"}
            </button>
          </div>
        </div>
        <button className="btn-primary" disabled={adding} onClick={addSingle}>
          {adding ? "..." : "افزودن"}
        </button>
      </div>

      {/* Bulk add */}
      <div className="card space-y-3">
        <h3 className="font-bold text-sm">افزودن گروهی</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label">ارائه‌دهنده</label>
            <select className="input" value={bulkProvider} onChange={(e) => setBulkProvider(e.target.value)}>
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="label">چند کلید (هر خط یک کلید)</label>
          <textarea
            className="input h-28"
            dir="ltr"
            placeholder={"sk-...\nsk-...\nsk-..."}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
          />
        </div>
        <button className="btn-secondary" disabled={bulkAdding} onClick={addBulk}>
          {bulkAdding ? "..." : "افزودن گروهی"}
        </button>
      </div>

      {/* Keys table */}
      <div className="card space-y-3">
        <h3 className="font-bold text-sm">کلیدها</h3>
        {loading && <Spinner />}
        {error && <div className="text-red-400 text-sm">{error}</div>}
        {keys && keys.length === 0 && !loading && <Empty label="کلیدی ثبت نشده است." />}
        {keys && keys.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-right border-b border-slate-700">
                  <th className="py-2 px-2 font-medium">ارائه‌دهنده</th>
                  <th className="py-2 px-2 font-medium">کلید</th>
                  <th className="py-2 px-2 font-medium">برچسب</th>
                  <th className="py-2 px-2 font-medium">وضعیت</th>
                  <th className="py-2 px-2 font-medium">موفق/ناموفق</th>
                  <th className="py-2 px-2 font-medium">آخرین بررسی</th>
                  <th className="py-2 px-2 font-medium">عملیات</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id} className={`border-b border-slate-800 ${k.is_active ? "" : "opacity-50"}`}>
                    <td className="py-2 px-2">
                      <span className={`badge ${PROVIDER_BADGE[k.provider] || PROVIDER_BADGE.openai}`}>
                        {PROVIDER_LABEL[k.provider] || k.provider}
                      </span>
                    </td>
                    <td className="py-2 px-2 font-mono text-xs" dir="ltr">{k.api_key_masked}</td>
                    <td className="py-2 px-2 truncate max-w-[10rem]">{k.label || "—"}</td>
                    <td className="py-2 px-2">
                      <span className={`badge ${STATUS_BADGE[k.status] || STATUS_BADGE.unknown}`} title={k.last_error || ""}>
                        {STATUS_LABEL[k.status] || k.status}
                      </span>
                    </td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      <span className="text-emerald-300">{fa(k.success_count)}</span>
                      {" / "}
                      <span className="text-red-300">{fa(k.fail_count)}</span>
                    </td>
                    <td className="py-2 px-2 text-xs text-slate-400 whitespace-nowrap">
                      {k.last_checked_at ? k.last_checked_at.slice(0, 16).replace("T", " ") : "—"}
                    </td>
                    <td className="py-2 px-2">
                      <div className="flex flex-wrap gap-1">
                        <button className="btn-secondary text-xs" disabled={testingId === k.id} onClick={() => testOne(k.id)}>
                          {testingId === k.id ? "..." : "تست"}
                        </button>
                        <button className="btn-secondary text-xs" onClick={() => editLabel(k)}>برچسب</button>
                        <button className="btn-secondary text-xs" onClick={() => editKey(k)}>ویرایش کلید</button>
                        <button className="btn-secondary text-xs" onClick={() => toggle(k)}>
                          {k.is_active ? "غیرفعال" : "فعال"}
                        </button>
                        <button className="btn-danger text-xs" onClick={() => remove(k.id)}>حذف</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
