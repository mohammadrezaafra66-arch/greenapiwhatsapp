import React from "react";
import { ReportingApi as Api } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";
import {
  TOP_PRODUCTS_RANGE_OPTIONS, TOP_PRODUCTS_DEFAULT_DAYS, TOP_PRODUCTS_DEFAULT_LIMIT,
} from "./reporting.js";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

const TABS = [
  { key: "emergency", label: "شماره‌های اضطراری" },
  { key: "daily", label: "گزارش روزانه" },
  { key: "mentions", label: "رصد محصولات در گروه‌ها" },
  { key: "topProducts", label: "جدول محصولات پر تکرار" },
  { key: "spotAlerts", label: "هشدار محصولات دیده‌شده" },
  { key: "bestHours", label: "بهترین ساعت ارسال" },
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

// Contact info cell: sender phone + any numbers found in the message, each with a
// copy button. The sender's own number is tagged "فرستنده".
function ContactCell({ contacts, senderPhone }) {
  const list = Array.isArray(contacts) ? contacts : [];
  const copy = async (phone) => {
    try {
      await navigator.clipboard.writeText(phone);
      toast.success("کپی شد");
    } catch {
      toast.error("کپی ناموفق بود");
    }
  };
  if (list.length === 0) return <span className="text-slate-600 text-xs">—</span>;
  return (
    <div className="flex flex-col gap-1">
      {list.map((phone, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="font-mono text-xs text-emerald-400" dir="ltr">{phone}</span>
          <button
            onClick={() => copy(phone)}
            className="text-slate-500 hover:text-slate-300 text-xs"
            title="کپی"
          >
            📋
          </button>
          {senderPhone && phone === senderPhone && (
            <span className="text-[10px] text-sky-400">فرستنده</span>
          )}
        </div>
      ))}
    </div>
  );
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
      {tab === "topProducts" && <TopProductsTab />}
      {tab === "spotAlerts" && <SpotAlertsTab />}
      {tab === "bestHours" && <BestHoursTab />}
    </div>
  );
}

// ── V40 PART 7: catalog-product-spotted alerts (price-free «spotted» alerts) ──
function SpotAlertsTab() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [unreadOnly, setUnreadOnly] = React.useState(false);
  const SRC = { pv: "پی‌وی", group: "گروه", status: "استوری" };

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setData(await Api.spotAlerts(unreadOnly));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [unreadOnly]);

  React.useEffect(() => {
    load();
  }, [load]);

  const markRead = async (id) => {
    try {
      await Api.markSpotAlertRead(id);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const alerts = data?.alerts || [];
  return (
    <div className="space-y-4">
      <div className="card bg-sky-500/10 border-sky-500/30 text-sky-200 text-sm">
        هشدار زمانی ثبت می‌شود که محصولی از دستیار توسط یک مخاطب بیرونی تبلیغ شود. این نسخه فقط
        «دیده‌شدن» را گزارش می‌کند و مقایسه‌ی قیمت ندارد (به‌محض افزوده‌شدن استخراج قیمت در آینده،
        به هشدار «قیمت‌شکنی» ارتقا می‌یابد).
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
          فقط خوانده‌نشده‌ها
        </label>
        <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">
          {fa(data?.unread_count)} خوانده‌نشده
        </span>
        <button className="btn-secondary text-xs" onClick={load}>🔄 تازه‌سازی</button>
      </div>

      {loading && !data && <Spinner />}
      {data && alerts.length === 0 && !loading && <Empty label="هشداری ثبت نشده." />}

      {alerts.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">مخاطب</th>
                <th className="text-right p-2">شماره</th>
                <th className="text-right p-2">محصول (در دستیار)</th>
                <th className="text-right p-2">منبع</th>
                <th className="text-right p-2">زمان</th>
                <th className="text-center p-2">وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} className={`border-b border-slate-800 ${a.is_read ? "opacity-60" : ""}`}>
                  <td className="p-2">{a.contact_name || "—"}</td>
                  <td className="p-2 text-slate-300" dir="ltr">{a.contact_phone}</td>
                  <td className="p-2 font-bold">{a.product_name}</td>
                  <td className="p-2 text-slate-300 text-xs">{SRC[a.source] || a.source}</td>
                  <td className="p-2 text-slate-400 text-xs" dir="ltr">{a.time_shamsi}</td>
                  <td className="p-2 text-center">
                    {a.is_read ? (
                      <span className="text-emerald-400 text-xs">خوانده‌شده</span>
                    ) : (
                      <button className="btn-secondary text-xs" onClick={() => markRead(a.id)}>علامت خوانده‌شده</button>
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
    if (!f.name || !f.phone) return toast.error("نام و شماره لازم است");
    setSaving(true);
    try {
      await Api.addEmergency({ name: f.name, phone: f.phone, purpose: f.purpose });
      setF({ name: "", phone: "", purpose: "" });
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!(await confirmDialog("حذف این شماره؟"))) return;
    try {
      await Api.deleteEmergency(id);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
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
    if (!f.phone) return toast.error("شماره لازم است");
    setSaving(true);
    try {
      await Api.addSubscriber({ name: f.name, phone: f.phone });
      setF({ name: "", phone: "" });
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!(await confirmDialog("حذف این گیرنده؟"))) return;
    try {
      await Api.deleteSubscriber(id);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
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
    if (!(await confirmDialog("لاگ رصد محصولات پاک شود؟"))) return;
    try {
      await Api.clearMentions();
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
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
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">فرستنده</th>
                <th className="text-right p-2">اطلاعات تماس</th>
                <th className="text-right p-2">گروه</th>
                <th className="text-right p-2">پیام</th>
                <th className="text-right p-2">زمان</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m, i) => (
                <tr key={i} className="border-b border-slate-800">
                  <td className="p-2 font-bold">{m.product}</td>
                  <td className="p-2">
                    <span className={`badge text-xs ${m.in_assistant ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-amber-500/20 text-amber-300 border-amber-500/40"}`}>
                      {m.assistant_status || (m.in_assistant ? "در دستیار داریم" : "خارج از دستیار")}
                    </span>
                  </td>
                  <td className="p-2">{m.sender_name || m.sender || "—"}</td>
                  <td className="p-2"><ContactCell contacts={m.all_contacts} senderPhone={m.sender_phone} /></td>
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

// ── Tab 5: Best send hours (V13.3) ────────────────────────────
function BestHoursTab() {
  const [data, setData] = React.useState(null);
  const [days, setDays] = React.useState(30);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setData(await Api.bestHours(days));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [days]);

  React.useEffect(() => { load(); }, [load]);

  const byHour = data?.by_hour || [];
  const best = new Set(data?.best_hours || []);
  const maxRead = Math.max(1, ...byHour.map((h) => h.read_pct));
  const hasData = byHour.some((h) => h.sent > 0);

  return (
    <div className="space-y-4">
      <div className="card flex items-end gap-3 flex-wrap">
        <div>
          <label className="label">بازه</label>
          <select className="input" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>۷ روز</option>
            <option value={30}>۳۰ روز</option>
            <option value={90}>۹۰ روز</option>
          </select>
        </div>
        {data?.best_hours?.length > 0 && (
          <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">
            بهترین ساعت‌ها برای ارسال: {data.best_hours.map((h) => fa(h)).join("، ")}
          </span>
        )}
      </div>

      {loading && !data && <Spinner />}
      {data && !hasData && (
        <div className="card text-sm text-slate-400">
          هنوز داده کافی ثبت نشده — با ارسال بیشتر، نرخ خوانده‌شدن به تفکیک ساعت اینجا نمایش داده می‌شود.
        </div>
      )}
      {hasData && (
        <div className="card overflow-x-auto">
          <div className="flex items-end gap-1 h-48 min-w-[600px]" dir="ltr">
            {byHour.map((h) => (
              <div
                key={h.hour}
                className="flex-1 flex flex-col items-center justify-end"
                title={`ساعت ${h.hour} — خوانده ${h.read_pct}٪ · تحویل ${h.delivered_pct}٪ · ارسال ${h.sent}`}
              >
                <div
                  className={`w-full rounded-t ${best.has(h.hour) ? "bg-emerald-500" : "bg-sky-600"}`}
                  style={{ height: `${(h.read_pct / maxRead) * 100}%` }}
                />
                <span className="text-[10px] text-slate-500 mt-1">{h.hour}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400 mt-2">
            نرخ خوانده‌شدن به تفکیک ساعت (به وقت تهران). ستون‌های سبز = بهترین ساعت‌ها (حداقل {fa(data?.min_sample)} ارسال).
          </p>
        </div>
      )}
    </div>
  );
}

// ── Tab 4: Top repeated products (auto-refresh 30s) ───────────
function TopProductsTab() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [days, setDays] = React.useState(TOP_PRODUCTS_DEFAULT_DAYS);
  const [limit, setLimit] = React.useState(TOP_PRODUCTS_DEFAULT_LIMIT);
  const [source, setSource] = React.useState(""); // "" | pv | group | status
  const [sellersModal, setSellersModal] = React.useState(null); // {product_name, sellers, loading}
  const [trendModal, setTrendModal] = React.useState(null); // {phone, data, loading}

  const openTrend = async (phone) => {
    if (!phone) return;
    setTrendModal({ phone, data: null, loading: true });
    try {
      const data = await Api.contactTrend(phone, 90);
      setTrendModal({ phone, data, loading: false });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
      setTrendModal({ phone, data: null, loading: false });
    }
  };

  const openSellersModal = async (productName) => {
    setSellersModal({ product_name: productName, sellers: [], loading: true });
    try {
      const res = await Api.productSellers(productName, days, 100);
      setSellersModal({ product_name: productName, sellers: res?.sellers || [], loading: false });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
      setSellersModal({ product_name: productName, sellers: [], loading: false });
    }
  };

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setData(await Api.topProducts(limit, days, source));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [days, limit, source]);

  const SOURCE_LABEL = { pv: "پی‌وی", group: "گروه", status: "استوری" };

  React.useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const rankClass = (rank) => {
    if (rank <= 10) return "bg-amber-500/20 text-amber-300 border-amber-500/40";
    if (rank <= 50) return "bg-slate-400/20 text-slate-200 border-slate-400/40";
    return "bg-slate-500/20 text-slate-300 border-slate-500/40";
  };

  const exportExcel = () => {
    const products = data?.products || [];
    if (!products.length) return toast.info("داده‌ای برای خروجی نیست");
    const header = ["رتبه", "نام محصول", "وضعیت دستیار", "منبع", "تعداد تکرار", "تعداد گروه/چت", "تعداد فرستنده", "آخرین ذکر"];
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [header.map(esc).join(",")];
    for (const p of products) {
      lines.push([
        p.rank,
        p.product_name,
        p.assistant_status || (p.in_assistant ? "در دستیار داریم" : "خارج از دستیار"),
        (p.sources || []).map((s) => SOURCE_LABEL[s] || s).join(" / "),
        p.mention_count,
        p.group_count,
        p.sender_count,
        p.last_mention_shamsi,
      ].map(esc).join(","));
    }
    const csv = lines.join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "top-products.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const products = data?.products || [];

  return (
    <div className="space-y-4">
      <div className="card flex items-end gap-3 flex-wrap">
        <div>
          <label className="label">بازه</label>
          <select className="input" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {TOP_PRODUCTS_RANGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">تعداد</label>
          <select className="input" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            <option value={50}>۵۰</option>
            <option value={100}>۱۰۰</option>
            <option value={150}>۱۵۰</option>
          </select>
        </div>
        <div>
          <label className="label">منبع</label>
          <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">همه منابع</option>
            <option value="pv">پی‌وی</option>
            <option value="group">گروه</option>
            <option value="status">استوری</option>
          </select>
        </div>
        <button className="btn-secondary" onClick={exportExcel}>📥 خروجی اکسل</button>
        <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40">{fa(data?.total_products)} محصول</span>
      </div>

      {loading && !data && <div className="text-sm text-slate-400">در حال بارگذاری...</div>}
      {data && products.length === 0 && !loading && (
        <div className="card text-sm text-slate-400">هنوز محصول پرتکراری ثبت نشده (از پیام‌های PV و گروه‌ها استخراج می‌شود).</div>
      )}

      {products.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">رتبه</th>
                <th className="text-right p-2">نام محصول</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">منبع</th>
                <th className="text-right p-2">تعداد تکرار</th>
                <th className="text-right p-2">تعداد گروه/چت</th>
                <th className="text-right p-2">تعداد فرستنده</th>
                <th className="text-right p-2">آخرین ذکر</th>
                <th className="text-center p-2">مشاهده فروشندگان اخیر</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.rank} className="border-b border-slate-800">
                  <td className="p-2">
                    <span className={`badge ${rankClass(p.rank)}`}>{fa(p.rank)}</span>
                  </td>
                  <td className="p-2 font-bold">{p.product_name}</td>
                  <td className="p-2">
                    <span className={`badge text-xs ${p.in_assistant ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-amber-500/20 text-amber-300 border-amber-500/40"}`}>
                      {p.assistant_status || (p.in_assistant ? "در دستیار داریم" : "خارج از دستیار")}
                    </span>
                  </td>
                  <td className="p-2 text-xs text-slate-300">
                    {(p.sources || []).map((s) => SOURCE_LABEL[s] || s).join("، ") || "—"}
                  </td>
                  <td className="p-2">{fa(p.mention_count)}</td>
                  <td className="p-2 text-slate-300">{fa(p.group_count)}</td>
                  <td className="p-2 text-slate-300">{fa(p.sender_count)}</td>
                  <td className="p-2 text-xs text-slate-500">{p.last_mention_shamsi || "—"}</td>
                  <td className="p-2 text-center">
                    <button
                      onClick={() => openSellersModal(p.product_name)}
                      className="text-xs bg-emerald-700 hover:bg-emerald-600 text-white px-3 py-1 rounded whitespace-nowrap"
                    >
                      👁 مشاهده ({fa(p.sender_count)})
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sellersModal && (
        <SellersModal modal={sellersModal} days={days} onClose={() => setSellersModal(null)}
          onOpenTrend={openTrend} />
      )}
      {trendModal && (
        <ContactTrendModal modal={trendModal} onClose={() => setTrendModal(null)} />
      )}
    </div>
  );
}

// V40 PART 6 — per-contact advertising trend over time (unified across pv/group/status).
function ContactTrendModal({ modal, onClose }) {
  const SRC = { pv: "پی‌وی", group: "گروه", status: "استوری" };
  const d = modal.data;
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="p-3 border-b border-slate-700 flex items-center justify-between">
          <h3 className="font-bold">روند تبلیغات مخاطب · <span dir="ltr">{modal.phone}</span></h3>
          <button className="text-slate-400 hover:text-white" onClick={onClose}>✕</button>
        </div>
        <div className="p-3 overflow-auto space-y-4">
          {modal.loading && <div className="text-center py-8 text-slate-500">در حال بارگذاری...</div>}
          {d && d.total_mentions === 0 && !modal.loading && (
            <div className="text-center py-8 text-slate-500">تبلیغی از این مخاطب ثبت نشده.</div>
          )}
          {d && d.summary?.length > 0 && (
            <div>
              <p className="text-sm text-slate-400 mb-2">خلاصه‌ی تکرار محصولات (۹۰ روز اخیر):</p>
              <div className="flex flex-wrap gap-2">
                {d.summary.map((s, i) => (
                  <span key={i} className={`badge text-xs ${s.in_assistant ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-amber-500/20 text-amber-300 border-amber-500/40"}`}>
                    {fa(s.count)}× {s.product_name}
                  </span>
                ))}
              </div>
            </div>
          )}
          {d && d.timeline?.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="py-2 text-right">زمان</th>
                  <th className="py-2 text-right">منبع</th>
                  <th className="py-2 text-right">محصول</th>
                  <th className="py-2 text-right">وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {d.timeline.map((t, i) => (
                  <tr key={i} className="border-b border-slate-800">
                    <td className="py-2 text-slate-400 text-xs" dir="ltr">{t.time_shamsi}</td>
                    <td className="py-2 text-slate-300 text-xs">{SRC[t.source] || t.source}</td>
                    <td className="py-2">{t.product_name || "—"}</td>
                    <td className="py-2">
                      <span className={`badge text-xs ${t.in_assistant ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-amber-500/20 text-amber-300 border-amber-500/40"}`}>
                        {t.assistant_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// Feature B — per-product recent-sellers modal.
function SellersModal({ modal, days, onClose, onOpenTrend }) {
  const exportCsv = () => {
    const sellers = modal.sellers || [];
    if (!sellers.length) return toast.info("داده‌ای برای خروجی نیست");
    const header = ["فرستنده", "اطلاعات تماس", "گروه", "زمان", "پیام"];
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [header.map(esc).join(",")];
    for (const s of sellers) {
      lines.push(
        [s.sender_name, (s.all_contacts || []).join(" | "), s.group_name, s.time_shamsi, s.message_preview]
          .map(esc)
          .join(",")
      );
    }
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sellers-${modal.product_name}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-xl max-w-3xl w-full max-h-[80vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-slate-700 flex justify-between items-center">
          <div>
            <h3 className="font-bold text-white">فروشندگان اخیر</h3>
            <p className="text-sm text-slate-400">{modal.product_name}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-xl leading-none">✕</button>
        </div>

        <div className="overflow-y-auto p-4">
          {modal.loading ? (
            <div className="text-center py-8 text-slate-400">در حال بارگذاری...</div>
          ) : modal.sellers.length === 0 ? (
            <div className="text-center py-8 text-slate-500">فروشنده‌ای یافت نشد</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="py-2 text-right">فرستنده</th>
                  <th className="py-2 text-right">اطلاعات تماس</th>
                  <th className="py-2 text-right">گروه</th>
                  <th className="py-2 text-right">زمان</th>
                  <th className="py-2 text-center">روند</th>
                </tr>
              </thead>
              <tbody>
                {modal.sellers.map((s, i) => (
                  <tr key={i} className="border-b border-slate-800">
                    <td className="py-2">{s.sender_name || "—"}</td>
                    <td className="py-2">
                      <ContactCell contacts={s.all_contacts} senderPhone={s.sender_phone} />
                    </td>
                    <td className="py-2 text-slate-300 text-xs">{s.group_name || "—"}</td>
                    <td className="py-2 text-slate-400 text-xs" dir="ltr">{s.time_shamsi}</td>
                    <td className="py-2 text-center">
                      <button className="text-xs bg-sky-700 hover:bg-sky-600 text-white px-2 py-1 rounded whitespace-nowrap"
                        onClick={() => onOpenTrend && onOpenTrend(s.sender_phone || (s.all_contacts || [])[0])}>
                        📈 روند
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="p-3 border-t border-slate-700 flex items-center justify-between text-xs text-slate-500">
          <span>
            {fa(modal.sellers.length)} فروشنده در {fa(days)} روز اخیر
          </span>
          {modal.sellers.length > 0 && (
            <button className="btn-secondary text-xs" onClick={exportCsv}>📥 خروجی اکسل</button>
          )}
        </div>
      </div>
    </div>
  );
}
