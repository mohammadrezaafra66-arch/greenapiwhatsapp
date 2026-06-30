import React from "react";
import { Inbox as Api } from "../api.js";
import { Spinner, Empty, Modal } from "../ui.jsx";

const CAT_FA = {
  price_inquiry: "استعلام قیمت",
  complaint: "شکایت",
  order: "سفارش",
  unsubscribe: "لغو اشتراک",
  other: "سایر",
  uncategorized: "دسته‌بندی‌نشده",
};

export default function Inbox() {
  const [filter, setFilter] = React.useState({ unread: false, category: "" });
  const [data, setData] = React.useState(null);
  const [stats, setStats] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [reply, setReply] = React.useState(null);

  const load = React.useCallback(() => {
    setLoading(true);
    const params = {};
    if (filter.unread) params.unread = true;
    if (filter.category) params.category = filter.category;
    Promise.all([Api.list(params), Api.stats()])
      .then(([list, s]) => { setData(list); setStats(s); })
      .finally(() => setLoading(false));
  }, [filter]);

  React.useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold">صندوق ورودی</h2>
        <div className="flex flex-wrap gap-2 items-center">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={filter.unread} onChange={(e) => setFilter({ ...filter, unread: e.target.checked })} />
            فقط خوانده‌نشده
          </label>
          <select className="input w-auto" value={filter.category} onChange={(e) => setFilter({ ...filter, category: e.target.value })}>
            <option value="">همه دسته‌ها</option>
            {Object.entries(CAT_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      </div>

      {stats && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="badge bg-purple-500/20 text-purple-300 border-purple-500/40">خوانده‌نشده: {stats.unread}</span>
          {Object.entries(stats.by_category || {}).map(([k, v]) => (
            <span key={k} className="badge bg-slate-700 text-slate-300 border-slate-600">{CAT_FA[k] || k}: {v}</span>
          ))}
        </div>
      )}

      {loading && <Spinner />}
      {data && data.length === 0 && <Empty label="پیامی وجود ندارد." />}

      <div className="space-y-2">
        {data?.map((m) => (
          <div key={m.id} className={`card flex justify-between items-start gap-3 ${!m.is_read ? "border-brand/40" : ""}`}>
            <div className="flex-1">
              <p className="text-sm">
                <span className="font-bold text-emerald-300">{m.sender_name || m.sender_phone}</span>
                {m.is_group && <span className="text-xs text-purple-300"> (گروه)</span>}
                {m.category && <span className="badge mr-2 bg-slate-700 text-slate-300 border-slate-600">{CAT_FA[m.category] || m.category}</span>}
                {m.auto_replied && <span className="badge mr-1 bg-sky-500/20 text-sky-300 border-sky-500/40">پاسخ خودکار</span>}
              </p>
              <p className="text-slate-300 text-sm mt-1">{m.text || "—"}</p>
              <p className="text-xs text-slate-500 mt-1 font-mono">{m.sender_phone}</p>
            </div>
            <div className="flex flex-col gap-1">
              {!m.is_read && <button className="btn-secondary text-xs py-1" onClick={async () => { await Api.markRead(m.id); load(); }}>خواندم</button>}
              <button className="btn-primary text-xs py-1" onClick={() => setReply(m)}>پاسخ</button>
            </div>
          </div>
        ))}
      </div>

      {reply && <ReplyModal msg={reply} onClose={() => setReply(null)} onDone={load} />}
    </div>
  );
}

function ReplyModal({ msg, onClose, onDone }) {
  const [text, setText] = React.useState("");
  const [sending, setSending] = React.useState(false);

  const send = async () => {
    if (!text) return;
    setSending(true);
    try {
      const r = await Api.reply(msg.id, text);
      alert(r.sent ? "ارسال شد" : "ارسال ناموفق");
      onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal title={`پاسخ به ${msg.sender_name || msg.sender_phone}`} onClose={onClose}>
      <div className="space-y-3">
        <div className="card bg-slate-900 text-sm text-slate-300">{msg.text}</div>
        <textarea className="input h-24" value={text} onChange={(e) => setText(e.target.value)} placeholder="متن پاسخ..." />
        <button className="btn-primary w-full" disabled={sending} onClick={send}>{sending ? "در حال ارسال..." : "ارسال پاسخ"}</button>
      </div>
    </Modal>
  );
}
