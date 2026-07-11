import React from "react";
import { BlacklistApi as Api } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";
import { toast } from "../ui/toast.jsx";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

const OPTOUT_REASON_FA = {
  opt_out_keyword: "پاسخ لغو (کلمه کلیدی)",
  blocked: "بلاک کرد",
};

// V13.4 — auto opt-out log section
function OptOutSection() {
  const { data, loading } = useAsync(Api.optOutLog, []);
  const logs = data?.logs || [];
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg font-bold">لغو خودکار</h3>
        {data && (
          <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">
            {fa(data.week_count)} نفر این هفته لغو کردند
          </span>
        )}
      </div>
      {loading && <Spinner />}
      {data && logs.length === 0 && <p className="text-sm text-slate-500">هنوز لغو خودکاری ثبت نشده.</p>}
      {logs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-right">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="py-2 px-2 font-medium">شماره</th>
                <th className="py-2 px-2 font-medium">دلیل</th>
                <th className="py-2 px-2 font-medium">زمان</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-b border-slate-800">
                  <td className="py-2 px-2 font-mono text-xs">{l.phone}</td>
                  <td className="py-2 px-2">{OPTOUT_REASON_FA[l.reason] || l.reason}</td>
                  <td className="py-2 px-2 text-xs text-slate-500">{new Date(l.created_at).toLocaleString("fa-IR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Blacklist() {
  const { data, loading, error, reload } = useAsync(Api.list, []);
  const [phone, setPhone] = React.useState("");
  const [reason, setReason] = React.useState("");

  const add = async () => {
    if (!phone) return toast.error("شماره لازم است");
    try {
      await Api.add(phone, reason || undefined);
      setPhone("");
      setReason("");
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4 max-w-2xl">
      <h2 className="text-2xl font-bold">لیست سیاه</h2>

      <OptOutSection />

      <div className="card flex flex-wrap gap-2 items-end">
        <div className="flex-1 min-w-[160px]">
          <label className="label">شماره</label>
          <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="989123456789" />
        </div>
        <div className="flex-1 min-w-[160px]">
          <label className="label">دلیل</label>
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <button className="btn-primary" onClick={add}>افزودن</button>
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="لیست سیاه خالی است." />}

      <div className="space-y-2">
        {data?.map((b) => (
          <div key={b.id} className="card flex items-center justify-between">
            <div>
              <p className="font-mono">{b.phone}</p>
              <p className="text-xs text-slate-500">{b.reason || "بدون دلیل"} · {new Date(b.created_at).toLocaleDateString("fa-IR")}</p>
            </div>
            <button className="btn-secondary" onClick={async () => { await Api.remove(b.phone); reload(); }}>حذف از لیست</button>
          </div>
        ))}
      </div>
    </div>
  );
}
