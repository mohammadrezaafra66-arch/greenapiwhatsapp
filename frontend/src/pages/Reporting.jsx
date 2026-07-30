import React from "react";
import { ReportingApi as Api } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";
import {
  TOP_PRODUCTS_RANGE_OPTIONS, TOP_PRODUCTS_LIMIT_OPTIONS,
  TOP_PRODUCTS_DEFAULT_DAYS, TOP_PRODUCTS_DEFAULT_LIMIT,
  loadTopProductsFilters, saveTopProductsFilters,
} from "./reporting.js";

const faNum = (n) => Number(n).toLocaleString("fa-IR", { useGrouping: false });

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
  if (list.length === 0) return <span className="text-muted text-xs">—</span>;
  return (
    <div className="flex flex-col gap-1">
      {list.map((phone, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="font-mono text-xs text-brand" dir="ltr">{phone}</span>
          <button
            onClick={() => copy(phone)}
            className="text-muted hover:text-ink text-xs"
            title="کپی"
          >
            📋
          </button>
          {senderPhone && phone === senderPhone && (
            <span className="text-[10px] text-sky-700">فرستنده</span>
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
            className={`px-3 py-2 rounded-lg text-sm ${tab === t.key ? "bg-brand-light text-brand" : "text-muted hover:bg-canvas"}`}
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
      <div className="card bg-sky-50 border-sky-200 text-sky-700 text-sm">
        هشدار زمانی ثبت می‌شود که محصولی از دستیار توسط یک مخاطب بیرونی تبلیغ شود. این نسخه فقط
        «دیده‌شدن» را گزارش می‌کند و مقایسه‌ی قیمت ندارد (به‌محض افزوده‌شدن استخراج قیمت در آینده،
        به هشدار «قیمت‌شکنی» ارتقا می‌یابد).
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
          فقط خوانده‌نشده‌ها
        </label>
        <span className="badge bg-amber-50 text-amber-700 border-amber-200">
          {fa(data?.unread_count)} خوانده‌نشده
        </span>
        <button className="btn-secondary btn-sm" onClick={load}>🔄 تازه‌سازی</button>
      </div>

      {loading && !data && <Spinner />}
      {data && alerts.length === 0 && !loading && <Empty label="هشداری ثبت نشده." />}

      {alerts.length > 0 && (
        <div className="table-wrap">
          <table className="table w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
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
                <tr key={a.id} className={`border-b border-line ${a.is_read ? "opacity-60" : ""}`}>
                  <td className="p-2">{a.contact_name || "—"}</td>
                  <td className="p-2 text-muted" dir="ltr">{a.contact_phone}</td>
                  <td className="p-2 font-bold">{a.product_name}</td>
                  <td className="p-2 text-muted text-xs">{SRC[a.source] || a.source}</td>
                  <td className="p-2 text-muted text-xs" dir="ltr">{a.time_shamsi}</td>
                  <td className="p-2 text-center">
                    {a.is_read ? (
                      <span className="text-brand text-xs">خوانده‌شده</span>
                    ) : (
                      <button className="btn-secondary btn-sm" onClick={() => markRead(a.id)}>علامت خوانده‌شده</button>
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
      {error && <div className="card bg-red-50 text-red-700 border-red-200">{error}</div>}
      {data && data.length === 0 && <Empty label="شماره‌ای ثبت نشده است." />}

      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
                <th className="text-right p-2">نام</th>
                <th className="text-right p-2">شماره</th>
                <th className="text-right p-2">نوع</th>
                <th className="text-right p-2">فعال</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id} className="border-b border-line">
                  <td className="p-2 font-bold">{c.name}</td>
                  <td className="p-2 font-mono text-xs">{c.phone}</td>
                  <td className="p-2 text-muted">{c.purpose || "—"}</td>
                  <td className="p-2">
                    <span className={`badge ${c.is_active ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`}>
                      {c.is_active ? "فعال" : "غیرفعال"}
                    </span>
                  </td>
                  <td className="p-2">
                    <button className="btn-danger btn-sm" onClick={() => remove(c.id)}>حذف</button>
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
      {error && <div className="card bg-red-50 text-red-700 border-red-200">{error}</div>}
      {data && data.length === 0 && <Empty label="گیرنده‌ای ثبت نشده است." />}

      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
                <th className="text-right p-2">نام</th>
                <th className="text-right p-2">شماره</th>
                <th className="text-right p-2">فعال</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id} className="border-b border-line">
                  <td className="p-2 font-bold">{s.name || "—"}</td>
                  <td className="p-2 font-mono text-xs">{s.phone}</td>
                  <td className="p-2">
                    <span className={`badge ${s.is_active ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`}>
                      {s.is_active ? "فعال" : "غیرفعال"}
                    </span>
                  </td>
                  <td className="p-2">
                    <button className="btn-danger btn-sm" onClick={() => remove(s.id)}>حذف</button>
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
      {error && <div className="card bg-red-50 text-red-700 border-red-200">{error}</div>}
      {rows && rows.length === 0 && !loading && <Empty label="گزارشی برای این روز نیست." />}

      {rows && rows.length > 0 && (
        <div className="table-wrap">
          <table className="table w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
                <th className="text-right p-2">حساب</th>
                <th className="text-right p-2">کمپین</th>
                <th className="text-right p-2">گیرنده</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">زمان</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-line">
                  <td className="p-2">{r.account_name || "—"}</td>
                  <td className="p-2">{r.campaign_name || "—"}</td>
                  <td className="p-2">
                    <div>{r.recipient_name || "—"}</div>
                    <div className="font-mono text-xs text-muted">{r.recipient_phone}</div>
                  </td>
                  <td className="p-2">{r.status || "—"}</td>
                  <td className="p-2 text-xs text-muted">{tsFmt(r.sent_at)}</td>
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
        <p className="text-sm text-muted">هر ۳۰ ثانیه بروزرسانی می‌شود.</p>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={load}>بروزرسانی</button>
          <button className="btn-danger" onClick={clear}>پاک کردن لاگ</button>
        </div>
      </div>

      {loading && !rows && <Spinner />}
      {error && <div className="card bg-red-50 text-red-700 border-red-200">{error}</div>}
      {rows && rows.length === 0 && <Empty label="موردی ثبت نشده است." />}

      {rows && rows.length > 0 && (
        <div className="table-wrap">
          <table className="table w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
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
                <tr key={i} className="border-b border-line">
                  <td className="p-2 font-bold">{m.product}</td>
                  <td className="p-2">
                    <span className={`badge text-xs ${m.in_assistant ? "bg-brand-light text-brand border-brand/30" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
                      {m.assistant_status || (m.in_assistant ? "در دستیار داریم" : "خارج از دستیار")}
                    </span>
                  </td>
                  <td className="p-2">{m.sender_name || m.sender || "—"}</td>
                  <td className="p-2"><ContactCell contacts={m.all_contacts} senderPhone={m.sender_phone} /></td>
                  <td className="p-2 text-muted">{m.group || "—"}</td>
                  <td className="p-2 text-muted">
                    {String(m.text || "").slice(0, 50)}
                    {String(m.text || "").length > 50 ? "…" : ""}
                  </td>
                  <td className="p-2 text-xs text-muted">{tsFmt(m.time)}</td>
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
          <span className="badge bg-brand-light text-brand border-brand/30">
            بهترین ساعت‌ها برای ارسال: {data.best_hours.map((h) => fa(h)).join("، ")}
          </span>
        )}
      </div>

      {loading && !data && <Spinner />}
      {data && !hasData && (
        <div className="card text-sm text-muted">
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
                  className={`w-full rounded-t ${best.has(h.hour) ? "bg-brand" : "bg-sky-500"}`}
                  style={{ height: `${(h.read_pct / maxRead) * 100}%` }}
                />
                <span className="text-[10px] text-muted mt-1">{h.hour}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted mt-2">
            نرخ خوانده‌شدن به تفکیک ساعت (به وقت تهران). ستون‌های سبز = بهترین ساعت‌ها (حداقل {fa(data?.min_sample)} ارسال).
          </p>
        </div>
      )}
    </div>
  );
}

// ── Tab 4: Top repeated products (auto-refresh 30s) ───────────
function TopProductsTab() {
  const initialFilters = React.useMemo(() => loadTopProductsFilters(), []);
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [days, setDays] = React.useState(initialFilters.days || TOP_PRODUCTS_DEFAULT_DAYS);
  const [limit, setLimit] = React.useState(initialFilters.limit || TOP_PRODUCTS_DEFAULT_LIMIT);
  const [source, setSource] = React.useState(initialFilters.source || ""); // "" | pv | group | status
  const [aiMerge, setAiMerge] = React.useState(Boolean(initialFilters.aiMerge));
  const [searchInput, setSearchInput] = React.useState(initialFilters.search || ""); // raw text field value
  const [search, setSearch] = React.useState(initialFilters.search || ""); // debounced value sent to the backend
  const [sellersModal, setSellersModal] = React.useState(null); // {product_name, sellers, loading}
  const [trendModal, setTrendModal] = React.useState(null); // {phone, data, loading}

  // V44 — debounce the search box so we send at most one request per pause, not per keystroke.
  React.useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  React.useEffect(() => {
    saveTopProductsFilters({ days, limit, source, search, aiMerge });
  }, [days, limit, source, search, aiMerge]);

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

  const openSellersModal = async (product) => {
    const productName = product?.product_name || "";
    const canonicalKey = product?.canonical_key || "";
    const matchKeys = Array.isArray(product?.match_keys) ? product.match_keys : [];
    setSellersModal({ product_name: productName, sellers: [], loading: true });
    try {
      const res = await Api.productSellers(productName, days, 100, canonicalKey, matchKeys);
      setSellersModal({ product_name: productName, sellers: res?.sellers || [], loading: false });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
      setSellersModal({ product_name: productName, sellers: [], loading: false });
    }
  };

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setData(await Api.topProducts(limit, days, source, search, aiMerge));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [days, limit, source, search, aiMerge]);

  const SOURCE_LABEL = { pv: "پی‌وی", group: "گروه", status: "استوری" };

  React.useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const rankClass = (rank) => {
    if (rank <= 10) return "bg-amber-50 text-amber-700 border-amber-200";
    if (rank <= 50) return "bg-slate-100 text-slate-700 border-slate-300";
    return "bg-slate-50 text-slate-500 border-slate-200";
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
            {TOP_PRODUCTS_LIMIT_OPTIONS.map((n) => (
              <option key={n} value={n}>{faNum(n)}</option>
            ))}
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
        <div className="flex-1 min-w-[12rem]">
          <label className="label">جستجوی محصول</label>
          <div className="relative">
            <input
              type="text"
              className="input w-full"
              placeholder="نام محصول..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => setSearchInput("")}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                title="پاک کردن"
              >
                ✕
              </button>
            )}
          </div>
        </div>
        <label className="flex items-center gap-2 h-10 text-sm text-ink">
          <input
            type="checkbox"
            checked={aiMerge}
            onChange={(e) => setAiMerge(e.target.checked)}
          />
          <span>ادغام هوشمند AI</span>
        </label>
        <button className="btn-secondary" onClick={exportExcel}>📥 خروجی اکسل</button>
        <span className="badge bg-slate-100 text-slate-600 border-slate-300">{fa(data?.total_products)} محصول</span>
      </div>

      {loading && !data && <div className="text-sm text-muted">در حال بارگذاری...</div>}
      {data && products.length === 0 && !loading && (
        <div className="card text-sm text-muted">
          {search.trim()
            ? `محصولی با نام «${search.trim()}» یافت نشد.`
            : "هنوز محصول پرتکراری ثبت نشده (از پیام‌های PV و گروه‌ها استخراج می‌شود)."}
        </div>
      )}

      {products.length > 0 && (
        <div className="table-wrap">
          <table className="table w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
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
                <tr key={p.rank} className="border-b border-line">
                  <td className="p-2">
                    <span className={`badge ${rankClass(p.rank)}`}>{fa(p.rank)}</span>
                  </td>
                  <td className="p-2 font-bold">{p.product_name}</td>
                  <td className="p-2">
                    <span className={`badge text-xs ${p.in_assistant ? "bg-brand-light text-brand border-brand/30" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
                      {p.assistant_status || (p.in_assistant ? "در دستیار داریم" : "خارج از دستیار")}
                    </span>
                  </td>
                  <td className="p-2 text-xs text-muted">
                    {(p.sources || []).map((s) => SOURCE_LABEL[s] || s).join("، ") || "—"}
                  </td>
                  <td className="p-2">{fa(p.mention_count)}</td>
                  <td className="p-2 text-muted">{fa(p.group_count)}</td>
                  <td className="p-2 text-muted">{fa(p.sender_count)}</td>
                  <td className="p-2 text-xs text-muted">{p.last_mention_shamsi || "—"}</td>
                  <td className="p-2 text-center">
                    <button
                      onClick={() => openSellersModal(p)}
                      className="btn-primary btn-sm whitespace-nowrap"
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
      <div className="bg-surface border border-line rounded-lg shadow-card w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="p-3 border-b border-line flex items-center justify-between">
          <h3 className="font-bold">روند تبلیغات مخاطب · <span dir="ltr">{modal.phone}</span></h3>
          <button className="text-muted hover:text-ink" onClick={onClose}>✕</button>
        </div>
        <div className="p-3 overflow-auto space-y-4">
          {modal.loading && <div className="text-center py-8 text-muted">در حال بارگذاری...</div>}
          {d && d.total_mentions === 0 && !modal.loading && (
            <div className="text-center py-8 text-muted">تبلیغی از این مخاطب ثبت نشده.</div>
          )}
          {d && d.summary?.length > 0 && (
            <div>
              <p className="text-sm text-muted mb-2">خلاصه‌ی تکرار محصولات (۹۰ روز اخیر):</p>
              <div className="flex flex-wrap gap-2">
                {d.summary.map((s, i) => (
                  <span key={i} className={`badge text-xs ${s.in_assistant ? "bg-brand-light text-brand border-brand/30" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
                    {fa(s.count)}× {s.product_name}
                  </span>
                ))}
              </div>
            </div>
          )}
          {d && d.timeline?.length > 0 && (
            <div className="table-wrap">
              <table className="table w-full text-sm">
                <thead>
                  <tr className="text-muted border-b border-line">
                    <th className="py-2 text-right">زمان</th>
                    <th className="py-2 text-right">منبع</th>
                    <th className="py-2 text-right">محصول</th>
                    <th className="py-2 text-right">وضعیت</th>
                  </tr>
                </thead>
                <tbody>
                  {d.timeline.map((t, i) => (
                    <tr key={i} className="border-b border-line">
                      <td className="py-2 text-muted text-xs" dir="ltr">{t.time_shamsi}</td>
                      <td className="py-2 text-muted text-xs">{SRC[t.source] || t.source}</td>
                      <td className="py-2">{t.product_name || "—"}</td>
                      <td className="py-2">
                        <span className={`badge text-xs ${t.in_assistant ? "bg-brand-light text-brand border-brand/30" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
                          {t.assistant_status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
        className="bg-surface border border-line rounded-xl shadow-card max-w-3xl w-full max-h-[80vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-line flex justify-between items-center">
          <div>
            <h3 className="font-bold text-ink">فروشندگان اخیر</h3>
            <p className="text-sm text-muted">{modal.product_name}</p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-ink text-xl leading-none">✕</button>
        </div>

        <div className="overflow-y-auto p-4">
          {modal.loading ? (
            <div className="text-center py-8 text-muted">در حال بارگذاری...</div>
          ) : modal.sellers.length === 0 ? (
            <div className="text-center py-8 text-muted">فروشنده‌ای یافت نشد</div>
          ) : (
            <div className="table-wrap">
              <table className="table w-full text-sm">
                <thead>
                  <tr className="text-muted border-b border-line">
                    <th className="py-2 text-right">فرستنده</th>
                    <th className="py-2 text-right">اطلاعات تماس</th>
                    <th className="py-2 text-right">گروه</th>
                    <th className="py-2 text-right">زمان</th>
                    <th className="py-2 text-center">روند</th>
                  </tr>
                </thead>
                <tbody>
                  {modal.sellers.map((s, i) => (
                    <tr key={i} className="border-b border-line">
                      <td className="py-2">{s.sender_name || "—"}</td>
                      <td className="py-2">
                        <ContactCell contacts={s.all_contacts} senderPhone={s.sender_phone} />
                      </td>
                      <td className="py-2 text-muted text-xs">{s.group_name || "—"}</td>
                      <td className="py-2 text-muted text-xs" dir="ltr">{s.time_shamsi}</td>
                      <td className="py-2 text-center">
                        <button className="text-xs bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 px-2 py-1 rounded whitespace-nowrap"
                          onClick={() => onOpenTrend && onOpenTrend(s.sender_phone || (s.all_contacts || [])[0])}>
                          📈 روند
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="p-3 border-t border-line flex items-center justify-between text-xs text-muted">
          <span>
            {fa(modal.sellers.length)} فروشنده در {fa(days)} روز اخیر
          </span>
          {modal.sellers.length > 0 && (
            <button className="btn-secondary btn-sm" onClick={exportCsv}>📥 خروجی اکسل</button>
          )}
        </div>
      </div>
    </div>
  );
}
