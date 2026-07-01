import React from "react";
import { JournalsApi as Api, Accounts } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";

const TABS = [
  { key: "incoming", label: "پیام‌های ورودی" },
  { key: "outgoing", label: "پیام‌های خروجی" },
  { key: "chats", label: "چت‌های فعال" },
];

const RANGES = [
  { minutes: 60, label: "آخر ۱ ساعت" },
  { minutes: 360, label: "آخر ۶ ساعت" },
  { minutes: 1440, label: "آخر ۲۴ ساعت" },
  { minutes: 10080, label: "آخر ۷ روز" },
];

function preview(m) {
  return (
    m.textMessage ||
    m.extendedTextMessage?.text ||
    m.caption ||
    m.typeMessage ||
    "—"
  );
}

function tsFmt(t) {
  if (!t) return "—";
  try {
    return new Date(t * 1000).toLocaleString("fa-IR");
  } catch {
    return String(t);
  }
}

export default function Journals() {
  const { data: accounts, loading: accLoading } = useAsync(() => Accounts.list(), []);
  const [accountId, setAccountId] = React.useState("");
  const [tab, setTab] = React.useState("incoming");
  const [minutes, setMinutes] = React.useState(1440);
  const [rows, setRows] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [queue, setQueue] = React.useState(null);

  const load = React.useCallback(async () => {
    if (!accountId) return;
    setLoading(true);
    setError(null);
    try {
      let res;
      if (tab === "incoming") res = (await Api.incoming(accountId, minutes)).messages;
      else if (tab === "outgoing") res = (await Api.outgoing(accountId, minutes)).messages;
      else res = (await Api.chats(accountId)).chats;
      setRows(res || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, [accountId, tab, minutes]);

  const loadQueue = React.useCallback(async () => {
    if (!accountId) return;
    try {
      setQueue(await Api.queueCount(accountId));
    } catch {
      setQueue(null);
    }
  }, [accountId]);

  React.useEffect(() => {
    load();
    loadQueue();
  }, [load, loadQueue]);

  const clearWebhooks = async () => {
    if (!confirm("پاک کردن صف webhook؟")) return;
    try {
      await Api.clearWebhooks(accountId);
      await loadQueue();
      alert("پاک شد");
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold">ژورنال پیام‌ها</h2>
        <div className="flex flex-wrap gap-2 items-center">
          {queue && (
            <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">
              صف: {queue.messages_in_queue} پیام · {queue.webhooks_in_queue} webhook
            </span>
          )}
          <button className="btn-secondary" onClick={() => { load(); loadQueue(); }}>بروزرسانی</button>
          {accountId && <button className="btn-danger" onClick={clearWebhooks}>پاک کردن صف webhook</button>}
        </div>
      </div>

      <div className="card grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="label">حساب</label>
          {accLoading ? (
            <Spinner />
          ) : (
            <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              <option value="">— یک حساب انتخاب کنید —</option>
              {accounts?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          )}
        </div>
        <div>
          <label className="label">بازه زمانی</label>
          <select className="input" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} disabled={tab === "chats"}>
            {RANGES.map((r) => <option key={r.minutes} value={r.minutes}>{r.label}</option>)}
          </select>
        </div>
      </div>

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

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {!accountId && <Empty label="ابتدا یک حساب انتخاب کنید." />}
      {accountId && rows && rows.length === 0 && !loading && <Empty label="موردی یافت نشد." />}

      {accountId && rows && rows.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                {tab === "chats" ? (
                  <>
                    <th className="text-right p-2">شناسه چت</th>
                    <th className="text-right p-2">نام</th>
                  </>
                ) : (
                  <>
                    <th className="text-right p-2">شماره / چت</th>
                    <th className="text-right p-2">نوع پیام</th>
                    <th className="text-right p-2">پیش‌نمایش</th>
                    <th className="text-right p-2">زمان</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((m, i) => (
                <tr key={m.idMessage || m.id || m.chatId || i} className="border-b border-slate-800">
                  {tab === "chats" ? (
                    <>
                      <td className="p-2 font-mono text-xs">{m.id || m.chatId}</td>
                      <td className="p-2">{m.name || "—"}</td>
                    </>
                  ) : (
                    <>
                      <td className="p-2 font-mono text-xs">{m.chatId || m.senderId || "—"}</td>
                      <td className="p-2">{m.typeMessage || "text"}</td>
                      <td className="p-2 text-slate-300">{String(preview(m)).slice(0, 60)}</td>
                      <td className="p-2 text-xs text-slate-500">{tsFmt(m.timestamp)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
