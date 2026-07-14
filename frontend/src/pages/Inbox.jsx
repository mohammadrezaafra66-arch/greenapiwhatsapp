import React from "react";
import { Inbox as Api, MessagesApi } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";
import { toast } from "../ui/toast.jsx";

const CAT_FA = {
  price_inquiry: "استعلام قیمت",
  complaint: "شکایت",
  order: "سفارش",
  unsubscribe: "لغو اشتراک",
  other: "سایر",
  uncategorized: "دسته‌بندی‌نشده",
};

const MSG_TYPE_FA = {
  call: "تماس 📲",
  button_reply: "پاسخ دکمه",
  poll_update: "رأی نظرسنجی",
  catalog_update: "آپدیت کاتالوگ 🛍️",
  outgoing_call: "تماس خروجی 📞",
  reaction: "ری‌اکشن 😀",
};

function renderSpecial(m) {
  if (m.message_type === "call") {
    return (
      <p className="text-sm text-amber-300 mt-1">
        📞 تماس {m.call_status === "missed" ? "از دست رفته" : m.call_status || ""}
      </p>
    );
  }
  if (m.message_type === "button_reply") {
    return (
      <p className="text-sm text-sky-300 mt-1">
        🔘 دکمه انتخاب‌شده: <b>{m.button_reply_title || m.text || "—"}</b>
      </p>
    );
  }
  if (m.message_type === "reaction") {
    return (
      <p className="text-sm text-pink-300 mt-1">
        {m.text || "😀"} <span className="text-xs text-slate-500">ری‌اکشن روی پیام شما</span>
      </p>
    );
  }
  if (m.message_type === "poll_update") {
    let votes = [];
    try {
      votes = JSON.parse(m.poll_votes || "[]");
    } catch {
      votes = [];
    }
    return (
      <div className="text-sm text-purple-300 mt-1">
        📊 آرای نظرسنجی:
        <ul className="list-disc pr-5 text-xs mt-1">
          {votes.length === 0 && <li>—</li>}
          {votes.map((v, i) => (
            <li key={i}>{v.optionName || v.name || JSON.stringify(v)}{Array.isArray(v.optionVoters) ? ` (${v.optionVoters.length})` : ""}</li>
          ))}
        </ul>
      </div>
    );
  }
  return null;
}

export default function Inbox() {
  const [filter, setFilter] = React.useState({ unread: false, category: "", msgType: "" });
  const [data, setData] = React.useState(null);
  const [stats, setStats] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [reply, setReply] = React.useState(null);
  const [richSend, setRichSend] = React.useState(null);

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
          <select className="input w-auto" value={filter.msgType} onChange={(e) => setFilter({ ...filter, msgType: e.target.value })}>
            <option value="">همه انواع پیام</option>
            {Object.entries(MSG_TYPE_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
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
        {data?.filter((m) => !filter.msgType || m.message_type === filter.msgType).map((m) => (
          <div key={m.id} className={`card flex justify-between items-start gap-3 ${!m.is_read ? "border-brand/40" : ""}`}>
            <div className="flex-1">
              <p className="text-sm">
                <span className="font-bold text-emerald-300">{m.sender_name || m.sender_phone}</span>
                {m.is_group && <span className="text-xs text-purple-300"> (گروه)</span>}
                {MSG_TYPE_FA[m.message_type] && <span className="badge mr-2 bg-indigo-500/20 text-indigo-300 border-indigo-500/40">{MSG_TYPE_FA[m.message_type]}</span>}
                {m.category && <span className="badge mr-2 bg-slate-700 text-slate-300 border-slate-600">{CAT_FA[m.category] || m.category}</span>}
                {m.auto_replied && <span className="badge mr-1 bg-sky-500/20 text-sky-300 border-sky-500/40">پاسخ خودکار</span>}
              </p>
              {renderSpecial(m)}
              {!MSG_TYPE_FA[m.message_type] && <p className="text-slate-300 text-sm mt-1">{m.text || "—"}</p>}
              <p className="text-xs text-slate-500 mt-1 font-mono">{m.sender_phone}</p>
            </div>
            <div className="flex flex-col gap-1">
              {!m.is_read && <button className="btn-secondary text-xs py-1" onClick={async () => { await Api.markRead(m.id); load(); }}>خواندم</button>}
              <button className="btn-primary text-xs py-1" onClick={() => setReply(m)}>پاسخ</button>
              {!m.is_group && <button className="btn-secondary text-xs py-1" onClick={() => setRichSend({ msg: m, mode: "contact" })}>کارت تماس</button>}
              {!m.is_group && <button className="btn-secondary text-xs py-1" onClick={() => setRichSend({ msg: m, mode: "location" })}>موقعیت</button>}
            </div>
          </div>
        ))}
      </div>

      {reply && <ReplyModal msg={reply} onClose={() => setReply(null)} onDone={load} />}
      {richSend && <RichSendModal msg={richSend.msg} mode={richSend.mode} onClose={() => setRichSend(null)} />}
    </div>
  );
}

// FEATURE 12/13 — send a saved contact card or a saved location to the sender.
function RichSendModal({ msg, mode, onClose }) {
  const isContact = mode === "contact";
  const { data, loading } = useAsync(
    () => (isContact ? MessagesApi.savedContacts() : MessagesApi.savedLocations()), [mode]);
  const [sel, setSel] = React.useState("");
  const [sending, setSending] = React.useState(false);

  const send = async () => {
    if (!sel) return toast.error(isContact ? "یک کارت انتخاب کنید" : "یک موقعیت انتخاب کنید");
    setSending(true);
    try {
      if (isContact) {
        await MessagesApi.sendContact({ chat_id: msg.sender_phone, saved_card_id: sel });
      } else {
        await MessagesApi.sendLocation({ chat_id: msg.sender_phone, saved_location_id: sel });
      }
      toast.success("ارسال شد");
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal title={`${isContact ? "ارسال کارت تماس" : "ارسال موقعیت"} به ${msg.sender_name || msg.sender_phone}`} onClose={onClose}>
      <div className="space-y-3">
        {loading ? <Spinner /> : (!data || data.length === 0) ? (
          <Empty label={isContact ? "کارتی ذخیره نشده — از «کارت تماس و موقعیت» اضافه کنید." : "موقعیتی ذخیره نشده — از «کارت تماس و موقعیت» اضافه کنید."} />
        ) : (
          <select className="input" value={sel} onChange={(e) => setSel(e.target.value)}>
            <option value="">— انتخاب —</option>
            {data.map((x) => (
              <option key={x.id} value={x.id}>{isContact ? `${x.label} (${x.phone_contact})` : `${x.name}`}</option>
            ))}
          </select>
        )}
        <button className="btn-primary w-full" disabled={sending || !sel} onClick={send}>
          {sending ? "در حال ارسال..." : "ارسال"}
        </button>
      </div>
    </Modal>
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
      toast.info(r.sent ? "ارسال شد" : "ارسال ناموفق");
      onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
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
