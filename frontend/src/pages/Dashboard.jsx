import React from "react";
import { Dashboard as DashApi, Inbox as InboxApi, AiApi } from "../api.js";
import { Spinner } from "../ui.jsx";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from "recharts";

// ── helpers ────────────────────────────────────────────────
const fa = (n) => Number(n ?? 0).toLocaleString("fa-IR");

function timeAgo(iso) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (isNaN(s)) return "—";
  if (s < 60) return "چند لحظه پیش";
  if (s < 3600) return `${fa(Math.floor(s / 60))} دقیقه پیش`;
  if (s < 86400) return `${fa(Math.floor(s / 3600))} ساعت پیش`;
  return `${fa(Math.floor(s / 86400))} روز پیش`;
}

const CAT = {
  price_inquiry: { fa: "استعلام قیمت", c: "bg-sky-500/20 text-sky-300 border-sky-500/40" },
  complaint: { fa: "شکایت", c: "bg-red-500/20 text-red-300 border-red-500/40" },
  order: { fa: "سفارش", c: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
  unsubscribe: { fa: "لغو اشتراک", c: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
  other: { fa: "سایر", c: "bg-slate-600/40 text-slate-300 border-slate-500/40" },
};

const STATUS_FA = { active: "فعال", banned: "مسدود", disconnected: "قطع", pending: "در انتظار" };
const STATUS_DOT = { active: "bg-emerald-400", banned: "bg-red-400", disconnected: "bg-yellow-400", pending: "bg-slate-400" };

// ── count-up animated number ───────────────────────────────
function AnimatedNumber({ value = 0, className = "" }) {
  const [display, setDisplay] = React.useState(value);
  const prev = React.useRef(value);
  React.useEffect(() => {
    const start = prev.current;
    const end = Number(value) || 0;
    if (start === end) { setDisplay(end); return; }
    const dur = 600;
    const t0 = performance.now();
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(Math.round(start + (end - start) * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
      else prev.current = end;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className={className}>{fa(display)}</span>;
}

// ── KPI card ───────────────────────────────────────────────
function Kpi({ label, icon, children, accent = "text-slate-100", pulse = false }) {
  return (
    <div className="card relative overflow-hidden">
      <div className="flex items-start justify-between">
        <p className="text-slate-400 text-sm">{label}</p>
        <span className="text-xl opacity-80">
          {icon}
          {pulse && <span className="inline-block w-2 h-2 mr-1 rounded-full bg-amber-400 animate-pulse align-middle" />}
        </span>
      </div>
      <div className={`text-4xl font-bold mt-3 ${accent}`}>{children}</div>
    </div>
  );
}

const CHART_TOOLTIP = {
  contentStyle: { background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#cbd5e1" },
  itemStyle: { color: "#e2e8f0" },
};

export default function Dashboard() {
  const [stats, setStats] = React.useState(null);
  const [rl, setRl] = React.useState(null);
  const [inbox, setInbox] = React.useState([]);
  const [ai, setAi] = React.useState({ stats: [], providers: {} });
  const [err, setErr] = React.useState(null);
  const [updated, setUpdated] = React.useState(null);

  const load = React.useCallback(async () => {
    try {
      const [s, r, msgs] = await Promise.all([
        DashApi.stats(),
        DashApi.rateLimits(),
        InboxApi.list({ limit: 10 }).catch(() => []),
      ]);
      setStats(s); setRl(r); setInbox(Array.isArray(msgs) ? msgs : []);
      setErr(null); setUpdated(new Date());
    } catch (e) {
      setErr(e?.message || "خطا");
    }
  }, []);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  // AI usage polls on a slower 30s cadence
  const loadAi = React.useCallback(async () => {
    try {
      const [s, p] = await Promise.all([AiApi.stats(), AiApi.providers()]);
      setAi({ stats: Array.isArray(s) ? s : [], providers: p || {} });
    } catch {
      /* non-fatal */
    }
  }, []);
  React.useEffect(() => {
    loadAi();
    const t = setInterval(loadAi, 30000);
    return () => clearInterval(t);
  }, [loadAi]);

  if (!stats && !err) return <Spinner />;
  if (err && !stats)
    return (
      <div className="card text-red-400">
        خطا در اتصال به بک‌اند: {err}
        <p className="text-slate-400 text-sm mt-2">
          مطمئن شوید بک‌اند روی <code>http://localhost:8002</code> در حال اجراست.
        </p>
      </div>
    );

  const detail = stats.accounts.detail || [];
  const activeCount = stats.accounts.active ?? 0;
  const totalCount = stats.accounts.total ?? 0;

  // charts data
  const barData = detail.map((a) => ({ name: a.name, sent: a.sent_today || 0 }));
  const statusCounts = detail.reduce((m, a) => ((m[a.status] = (m[a.status] || 0) + 1), m), {});
  const pieData = [
    { name: "فعال", value: statusCounts.active || 0, color: "#10b981" },
    { name: "مسدود", value: statusCounts.banned || 0, color: "#ef4444" },
    { name: "قطع", value: statusCounts.disconnected || 0, color: "#eab308" },
    { name: "در انتظار", value: statusCounts.pending || 0, color: "#64748b" },
  ].filter((d) => d.value > 0);

  // rate-limiter 24h strip
  const maxAtHour = (h) => {
    for (const s of rl?.schedule || []) if (s.hour_start <= h && h < s.hour_end) return s.max_per_hour;
    return 0;
  };
  const curHour = rl?.current_hour ?? stats.rate_limiter.tehran_hour;
  const curMax = rl?.current_max ?? stats.rate_limiter.max_per_hour;
  const allowed = curMax > 0;

  // AI usage
  const AI_LABEL = { openai: "OpenAI", deepseek: "DeepSeek", gemini: "Gemini" };
  const aiOrder = ["openai", "deepseek", "gemini"];
  const aiStatOf = (k) => ai.stats.find((x) => x.provider === k) || { calls: 0, total_tokens: 0, errors: 0 };
  const aiBar = aiOrder.map((k) => ({ name: AI_LABEL[k], tokens: aiStatOf(k).total_tokens }));
  const aiTotalTokens = ai.stats.reduce((s, x) => s + (x.total_tokens || 0), 0);

  // quota warnings (kept from previous dashboard)
  const now = Date.now();
  const quotaHit = detail.filter(
    (a) => a.quota_exceeded_at && now - new Date(a.quota_exceeded_at).getTime() < 24 * 3600 * 1000
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">داشبورد زنده</h2>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          به‌روزرسانی خودکار هر ۵ ثانیه · {updated?.toLocaleTimeString("fa-IR")}
        </span>
      </div>

      {quotaHit.map((a) => (
        <div key={a.id} className="card bg-red-500/10 border-red-500/40 text-red-300">
          ⚠️ حساب {a.name} به سقف ارسال رسیده — تا فردا صبر کنید
        </div>
      ))}

      {/* ── TOP ROW: KPI cards ─────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi label="پیام‌های ارسالی امروز" icon="📤" accent="text-emerald-400">
          <AnimatedNumber value={stats.messages.sent_today} />
        </Kpi>
        <Kpi label="پیام‌های دریافتی امروز" icon="📥" accent="text-sky-400">
          <AnimatedNumber value={stats.messages.received_today} />
        </Kpi>
        <Kpi label="حساب‌های فعال / کل" icon="📱">
          <span className="text-emerald-400"><AnimatedNumber value={activeCount} /></span>
          <span className="text-slate-500 text-2xl"> / </span>
          <span className={totalCount - activeCount > 0 ? "text-red-400" : "text-slate-300"}>
            <AnimatedNumber value={totalCount} />
          </span>
        </Kpi>
        <Kpi label="کمپین‌های در حال اجرا" icon="🚀" accent="text-amber-400" pulse={stats.campaigns.active > 0}>
          <AnimatedNumber value={stats.campaigns.active} />
        </Kpi>
      </div>

      {/* ── CHARTS ROW ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="font-bold mb-3">ارسال امروز به تفکیک حساب</h3>
          {barData.length === 0 ? (
            <p className="text-slate-500 text-sm">حسابی وجود ندارد.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={barData} margin={{ top: 6, right: 8, left: -12, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <Tooltip {...CHART_TOOLTIP} cursor={{ fill: "#1e293b55" }} />
                <Bar dataKey="sent" name="ارسال امروز" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <h3 className="font-bold mb-3">وضعیت حساب‌ها</h3>
          {pieData.length === 0 ? (
            <p className="text-slate-500 text-sm">حسابی وجود ندارد.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                  innerRadius={55} outerRadius={90} paddingAngle={3}>
                  {pieData.map((d) => <Cell key={d.name} fill={d.color} stroke="#0f172a" />)}
                </Pie>
                <Tooltip {...CHART_TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 12, color: "#cbd5e1" }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ── AI USAGE PANEL ─────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="font-bold">مصرف هوش مصنوعی امروز</h3>
          <div className="flex items-center gap-3 flex-wrap">
            {aiOrder.map((k) => (
              <span key={k} className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className={`inline-block w-2 h-2 rounded-full ${ai.providers[k] ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
                {AI_LABEL[k]}
              </span>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
          <div>
            <p className="text-slate-400 text-sm">مجموع توکن مصرفی (۲۴ ساعت)</p>
            <p className="text-4xl font-bold mt-2 text-sky-400"><AnimatedNumber value={aiTotalTokens} /></p>
            <p className="text-xs text-slate-500 mt-2">
              {aiOrder.filter((k) => ai.providers[k]).length > 0
                ? `${fa(aiOrder.filter((k) => ai.providers[k]).length)} ارائه‌دهنده فعال`
                : "هیچ ارائه‌دهنده‌ای پیکربندی نشده"}
            </p>
          </div>
          <div className="md:col-span-2">
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={aiBar} margin={{ top: 6, right: 8, left: -12, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <Tooltip {...CHART_TOOLTIP} cursor={{ fill: "#1e293b55" }} />
                <Bar dataKey="tokens" name="توکن" fill="#38bdf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ── RATE LIMITER PANEL ─────────────────────────────── */}
      <div className="card space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h3 className="font-bold">محدودکننده نرخ ارسال</h3>
          <span className={`badge ${allowed ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-red-500/20 text-red-300 border-red-500/40"}`}>
            {allowed ? "مجاز ✅" : "متوقف 🔴"}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div>
            <p className="text-slate-400 text-sm">ساعت تهران</p>
            <p className="text-3xl font-bold mt-1">{fa(curHour)}:۰۰</p>
          </div>
          <div>
            <p className="text-slate-400 text-sm">حداکثر در این ساعت</p>
            <p className={`text-3xl font-bold mt-1 ${allowed ? "text-emerald-400" : "text-red-400"}`}>
              <AnimatedNumber value={curMax} />
            </p>
          </div>
          <div>
            <p className="text-slate-400 text-sm">وضعیت</p>
            <p className={`text-3xl font-bold mt-1 ${allowed ? "text-emerald-400" : "text-red-400"}`}>
              {allowed ? "باز" : "بسته"}
            </p>
          </div>
        </div>

        {/* 24h horizontal position bar */}
        <div>
          <div className="flex gap-0.5" dir="ltr">
            {Array.from({ length: 24 }, (_, h) => {
              const open = maxAtHour(h) > 0;
              const isNow = h === curHour;
              return (
                <div key={h} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    title={`${h}:00 → ${maxAtHour(h)}`}
                    className={`w-full h-6 rounded-sm ${open ? "bg-emerald-500/70" : "bg-slate-700"} ${isNow ? "ring-2 ring-amber-400" : ""}`}
                  />
                  {h % 3 === 0 && <span className="text-[9px] text-slate-500">{h}</span>}
                </div>
              );
            })}
          </div>
          <p className="text-xs text-slate-500 mt-2">نوار سبز = بازه مجاز ارسال · قاب زرد = ساعت فعلی</p>
        </div>

        {/* schedule table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">بازه ساعت</th>
                <th className="text-right p-2">حداکثر در ساعت</th>
              </tr>
            </thead>
            <tbody>
              {(rl?.schedule || []).map((s, i) => {
                const active = s.hour_start <= curHour && curHour < s.hour_end;
                return (
                  <tr key={i} className={`border-b border-slate-800 ${active ? "bg-emerald-500/10" : ""}`}>
                    <td className="p-2">{fa(s.hour_start)}:۰۰ — {fa(s.hour_end)}:۰۰</td>
                    <td className="p-2 font-bold">{fa(s.max_per_hour)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── INBOX + ACCOUNTS ───────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Inbox panel */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold">آخرین پیام‌ها</h3>
            <span className="badge bg-purple-500/20 text-purple-300 border-purple-500/40">
              خوانده‌نشده: <AnimatedNumber value={stats.messages.unread} />
            </span>
          </div>
          {inbox.length === 0 ? (
            <p className="text-slate-500 text-sm">پیامی وجود ندارد.</p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {inbox.map((m) => {
                const cat = CAT[m.category] || CAT.other;
                return (
                  <div key={m.id} className={`rounded-lg border p-2 ${m.is_read ? "border-slate-700 bg-slate-900/40" : "border-brand/40 bg-slate-900"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs text-slate-300">{m.sender_phone}</span>
                      <span className="flex items-center gap-2">
                        <span className={`badge ${cat.c}`}>{cat.fa}</span>
                        <span className="text-[11px] text-slate-500">{timeAgo(m.received_at)}</span>
                      </span>
                    </div>
                    <p className="text-sm text-slate-300 mt-1 truncate">
                      {(m.text || "—").slice(0, 40)}{(m.text || "").length > 40 ? "…" : ""}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Accounts status cards */}
        <div className="card">
          <h3 className="font-bold mb-3">وضعیت حساب‌ها</h3>
          {detail.length === 0 ? (
            <p className="text-slate-500 text-sm">حسابی ثبت نشده است.</p>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {detail.map((a) => (
                <div key={a.id} className="rounded-lg border border-slate-700 p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="flex items-center gap-2 font-bold">
                      <span className={`inline-block w-2.5 h-2.5 rounded-full ${STATUS_DOT[a.status] || "bg-slate-400"} ${a.status === "active" ? "animate-pulse" : ""}`} />
                      {a.name}
                      {a.warmup_enabled && <span className="badge bg-orange-500/20 text-orange-300 border-orange-500/40">🔥 گرم‌سازی</span>}
                    </span>
                    <span className="text-xs text-slate-400">{STATUS_FA[a.status] || a.status}</span>
                  </div>
                  <p className="text-xs text-slate-500 mb-2">{a.phone || "بدون شماره"}</p>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">ارسال امروز</span>
                    <span className="font-bold"><AnimatedNumber value={a.sent_today} /> / {fa(a.daily_limit)}</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-emerald-500 h-2 rounded-full transition-all duration-700"
                      style={{ width: `${a.daily_limit > 0 ? Math.min(100, (a.sent_today / a.daily_limit) * 100) : 0}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
