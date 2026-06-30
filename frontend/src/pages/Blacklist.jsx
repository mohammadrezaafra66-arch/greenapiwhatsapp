import React from "react";
import { BlacklistApi as Api } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";

export default function Blacklist() {
  const { data, loading, error, reload } = useAsync(Api.list, []);
  const [phone, setPhone] = React.useState("");
  const [reason, setReason] = React.useState("");

  const add = async () => {
    if (!phone) return alert("شماره لازم است");
    try {
      await Api.add(phone, reason || undefined);
      setPhone("");
      setReason("");
      reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4 max-w-2xl">
      <h2 className="text-2xl font-bold">لیست سیاه</h2>

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
