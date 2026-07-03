import React from "react";
import { ReportingApi as Api } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";

const TABS = [
  { key: "emergency", label: "شماره‌های اضطراری" },
  { key: "daily", label: "گزارش روزانه" },
  { key: "mentions", label: "رصد محصولات در گروه‌ها" },
];

function today() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function tsFmt(t) {
  if (!t) return "—";
  try {
    return new Date(t).toLocaleString("fa-IR");
  } catch {
    return String(t);
  }
}

export default function Reporting() {
  const [tab, setTab] = React.useState("emergency");

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">گزارش‌ها</h2>

      <div className="flex gap-2 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`px-3 py-2 rounded-lg text-sm ${tab === t.key ? "bg-brand/20 text-brand" : "text-slate-300 hover:bg-slate-800"}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "emergency" && <EmergencyTab />}
      {tab === "daily" && <DailyTab />}
      {tab === "mentions" && <MentionsTab />}
    </div>
  );
}

// ── Tab 1: Emergency contacts + night-report subscribers ──────
function EmergencyTab() {
  return (
    <div className="space-y-6">
      <EmergencySection />
      <SubscribersSection />
    </div>
  );
}

function EmergencySection() {
  const { data, loading, error, reload } = useAsync(() => Api.emergencyContacts(), []);
  const [f, setF] = React.useState({ name: "", phone: "", purpose: "" });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const add = async () => {
    if (!f.name || !f.phone) return alert("نام و شماره لازم است");
    setSaving(true);
    try {
      await Api.addEmergency({ name: f.name, phone: f.phone, purpose: f.purpose });
      setF({ name: "", phone: "", purpose: "" });
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!confirm("حذف این شماره؟")) return;
    try {
      await Api.deleteEmergency(id);
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-bold">شماره‌های اضطراری</h3>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="شماره‌ای ثبت نشده است." />}

      {data && data.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">نام</th>
                <th className="text-right p-2">شماره</th>
                <th className="text-right p-2">نوع</th>
                <th className="text-right p-2">فعال</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id} className="border-b border-slate-800">
                  <td className="p-2 font-bold">{c.name}</td>
                  <td className="p-2 font-mono text-xs">{c.phone}</td>
                  <td className="p-2 text-slate-300">{c.purpose || "—"}</td>
                  <td className="p-2">
                    <span className={`badge ${c.is_active ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-500/20 text-slate-300 border-slate-500/40"}`}>
                      {c.is_active ? "فعال" : "غیرفعال"}
                    </span>
                  </td>
                  <td className="p-2">
                    <button className="text-red-400 hover:underline" onClick={() => remove(c.id)}>حذف</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <div>
          <label className="label">نام</label>
          <input className="input" value={f.name} onChange={set("name")} />
        </div>
        <div>
          <label className="label">شماره</label>
          <input className="input" value={f.phone} onChange={set("phone")} />
        </div>
        <div>
          <label className="label">نوع</label>
          <input className="input" value={f.purpose} onChange={set("purpose")} placeholder="مثلاً پشتیبانی" />
        </div>
        <button className="btn-primary" disabled={saving} onClick={add}>{saving ? "..." : "افزودن"}</button>
      </div>
    </div>
  );
}

function SubscribersSection() {
  const { data, loading, error, reload } = useAsync(() => Api.subscribers(), []);
  const [f, setF] = React.useState({ name: "", phone: "" });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const add = async () => {
    if (!f.phone) return alert("شماره لازم است");
    setSaving(true);
    try {
      await Api.addSubscriber({ name: f.name, phone: f.phone });
      setF({ name: "", phone: "" });
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!confirm("حذف این گیرنده؟")) return;
    try {
      await Api.deleteSubscriber(id);
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-bold">گیرندگان گزارش شبانه</h3>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="گیرنده‌ای ثبت نشده است." />}

      {data && data.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">نام</th>
                <th className="text-right p-2">شماره</th>
                <th className="text-right p-2">فعال</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id} className="border-b border-slate-800">
                  <td className="p-2 font-bold">{s.name || "—"}</td>
                  <td className="p-2 font-mono text-xs">{s.phone}</td>
                  <td className="p-2">
                    <span className={`badge ${s.is_active ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-500/20 text-slate-300 border-slate-500/40"}`}>
                      {s.is_active ? "فعال" : "غیرفعال"}
                    </span>
                  </td>
                  <td className="p-2">
                    <button className="text-red-400 hover:underline" onClick={() => remove(s.id)}>حذف</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
        <div>
          <label className="label">نام</label>
          <input className="input" value={f.name} onChange={set("name")} />
        </div>
        <div>
          <label className="label">شماره</label>
          <input className="input" value={f.phone} onChange={set("phone")} />
        </div>
        <button className="btn-primary" disabled={saving} onClick={add}>{saving ? "..." : "افزودن"}</button>
      </div>
    </div>
  );
}

// ── Tab 2: Daily logs ─────────────────────────────────────────
function DailyTab() {
  const [date, setDate] = React.useState(today());
  const [rows, setRows] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows((await Api.dailyLogs(date)) || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, [date]);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="card">
        <label className="label">تاریخ</label>
        <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {rows && rows.length === 0 && !loading && <Empty label="گزارشی برای این روز نیست." />}

      {rows && rows.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">حساب</th>
                <th className="text-right p-2">کمپین</th>
                <th className="text-right p-2">گیرنده</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">زمان</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-800">
                  <td className="p-2">{r.account_name || "—"}</td>
                  <td className="p-2">{r.campaign_name || "—"}</td>
                  <td className="p-2">
                    <div>{r.recipient_name || "—"}</div>
                    <div className="font-mono text-xs text-slate-500">{r.recipient_phone}</div>
                  </td>
                  <td className="p-2">{r.status || "—"}</td>
                  <td className="p-2 text-xs text-slate-500">{tsFmt(r.sent_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Tab 3: Product mentions (auto-refresh 30s) ────────────────
function MentionsTab() {
  const [rows, setRows] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setRows((await Api.productMentions()) || []);
      setError(null);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const clear = async () => {
    if (!confirm("لاگ رصد محصولات پاک شود؟")) return;
    try {
      await Api.clearMentions();
      await load();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-500">هر ۳۰ ثانیه بروزرسانی می‌شود.</p>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={load}>بروزرسانی</button>
          <button className="btn-danger" onClick={clear}>پاک کردن لاگ</button>
        </div>
      </div>

      {loading && !rows && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {rows && rows.length === 0 && <Empty label="موردی ثبت نشده است." />}

      {rows && rows.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">محصول</th>
                <th className="text-right p-2">فرستنده</th>
                <th className="text-right p-2">گروه</th>
                <th className="text-right p-2">پیام</th>
                <th className="text-right p-2">زمان</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m, i) => (
                <tr key={i} className="border-b border-slate-800">
                  <td className="p-2 font-bold">{m.product}</td>
                  <td className="p-2">{m.sender_name || m.sender || "—"}</td>
                  <td className="p-2 text-slate-300">{m.group || "—"}</td>
                  <td className="p-2 text-slate-300">
                    {String(m.text || "").slice(0, 50)}
                    {String(m.text || "").length > 50 ? "…" : ""}
                  </td>
                  <td className="p-2 text-xs text-slate-500">{tsFmt(m.time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
