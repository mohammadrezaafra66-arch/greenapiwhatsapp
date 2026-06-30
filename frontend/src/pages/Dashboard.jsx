import React from "react";
import { Dashboard as DashApi } from "../api.js";
import { Badge, Progress, Spinner } from "../ui.jsx";

function Stat({ label, value, color = "text-slate-100" }) {
  return (
    <div className="card">
      <p className="text-slate-400 text-sm">{label}</p>
      <p className={`text-3xl font-bold mt-2 ${color}`}>{value ?? "—"}</p>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = React.useState(null);
  const [err, setErr] = React.useState(null);
  const [updated, setUpdated] = React.useState(null);

  const load = React.useCallback(() => {
    DashApi.stats()
      .then((d) => {
        setStats(d);
        setErr(null);
        setUpdated(new Date());
      })
      .catch((e) => setErr(e?.message || "خطا"));
  }, []);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  if (!stats && !err) return <Spinner />;
  if (err && !stats)
    return (
      <div className="card text-red-400">
        خطا در اتصال به بک‌اند: {err}
        <p className="text-slate-400 text-sm mt-2">
          مطمئن شوید بک‌اند روی <code>http://localhost:8000</code> در حال اجراست.
        </p>
      </div>
    );

  const rl = stats.rate_limiter;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">داشبورد</h2>
        <span className="text-xs text-slate-500">
          آخرین به‌روزرسانی: {updated?.toLocaleTimeString("fa-IR")}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="حساب‌های فعال" value={stats.accounts.active} color="text-emerald-400" />
        <Stat label="ارسال امروز" value={stats.messages.sent_today} color="text-sky-400" />
        <Stat label="کمپین فعال" value={stats.campaigns.active} color="text-amber-400" />
        <Stat label="پیام خوانده‌نشده" value={stats.messages.unread} color="text-purple-400" />
      </div>

      <div className="card">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <p className="text-slate-400 text-sm">وضعیت ارسال</p>
            <p className={`text-xl font-bold mt-1 ${rl.is_sending_allowed ? "text-emerald-400" : "text-red-400"}`}>
              {rl.is_sending_allowed ? "✅ ارسال مجاز است" : "⛔ خارج از ساعت کاری"}
            </p>
          </div>
          <div className="text-sm text-slate-400">
            <p>ساعت تهران: <b className="text-slate-200">{rl.tehran_hour}:00</b></p>
            <p>حداکثر در ساعت: <b className="text-slate-200">{rl.max_per_hour}</b></p>
          </div>
        </div>
      </div>

      <div>
        <h3 className="font-bold mb-3">حساب‌ها</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {stats.accounts.detail.length === 0 && (
            <p className="text-slate-500 text-sm">حسابی ثبت نشده است.</p>
          )}
          {stats.accounts.detail.map((a) => (
            <div key={a.id} className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold">{a.name}</span>
                <Badge status={a.status} />
              </div>
              <p className="text-slate-400 text-sm mb-3">{a.phone || "—"}</p>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-400">ارسال امروز</span>
                <span className="font-bold">{a.sent_today} / {a.daily_limit}</span>
              </div>
              <Progress value={a.sent_today} max={a.daily_limit} color="bg-emerald-500" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
