import React from "react";
import { QueueApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import { toast } from "../ui/toast.jsx";

const fa = (n) => (n == null ? "" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

// Green API showMessagesQueue items nest the payload under a `body` OBJECT (the text is
// NOT at q.body / q.text). Extract safely across message types so a populated queue renders
// instead of crashing on `.slice` of an object or blanking out.
function queueItemType(q) {
  const b = q?.body && typeof q.body === "object" ? q.body : {};
  return q?.typeMessage || b.typeMessage || q?.type || b.type || "—";
}
function queueItemText(q) {
  const b = q?.body && typeof q.body === "object" ? q.body : null;
  const cand =
    (b && (b.textMessage ||
           b.extendedTextMessage?.text ||
           b.caption ||
           b.fileName ||
           b.message)) ||
    q?.textMessage ||
    q?.text ||
    q?.caption ||
    (typeof q?.body === "string" ? q.body : "") ||
    (typeof q?.message === "string" ? q.message : "");
  return typeof cand === "string" ? cand : "";
}

// FEATURE 20 — send-queue management (⭐ emergency stop).
export default function SendQueue() {
  const { data, loading, reload } = useAsync(() => QueueApi.summary(), []);

  if (loading) return <Spinner />;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">صف ارسال</h2>
      <p className="text-sm text-amber-300">
        💡 نکته: پیش از اتصال مجدد یک شماره، صف ارسال آن را بررسی و در صورت لزوم خالی کنید.
      </p>
      {(!data?.accounts || data.accounts.length === 0) ? (
        <Empty label="هیچ حساب فعالی وجود ندارد." />
      ) : (
        <div className="space-y-3">
          {data.accounts.map((a) => (
            <QueueCard key={a.account_id} acc={a} onChange={reload} />
          ))}
        </div>
      )}
    </div>
  );
}

function QueueCard({ acc, onChange }) {
  const [expanded, setExpanded] = React.useState(false);
  const [detail, setDetail] = React.useState(null);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [detailError, setDetailError] = React.useState("");
  const [confirmText, setConfirmText] = React.useState("");
  const [clearing, setClearing] = React.useState(false);
  const hasQueue = (acc.count || 0) > 0;

  async function loadDetail() {
    if (expanded) { setExpanded(false); return; }
    // Fix B — show a loading state and SURFACE errors, so a real Green API failure is
    // never indistinguishable from a genuinely empty queue.
    setExpanded(true);
    setDetailError("");
    setDetailLoading(true);
    try {
      setDetail(await QueueApi.get(acc.account_id));
    } catch (e) {
      setDetail(null);
      setDetailError(e?.response?.data?.detail || e.message || "دریافت پیام‌های صف ناموفق بود");
    } finally {
      setDetailLoading(false);
    }
  }

  async function clearQueue() {
    if (confirmText.trim() !== "پاک کن") return toast.error("برای تأیید، «پاک کن» را تایپ کنید");
    setClearing(true);
    try {
      await QueueApi.clear(acc.account_id);
      toast.success("صف خالی شد");
      setConfirmText("");
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setClearing(false);
    }
  }

  return (
    <div className={`card ${hasQueue ? "border-red-500/50 bg-red-500/5" : ""}`}>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="font-bold">{acc.name}</p>
          <p className={`text-lg font-bold ${hasQueue ? "text-red-300" : "text-slate-400"}`}>
            صف ارسال: {fa(acc.count || 0)} پیام در انتظار
          </p>
        </div>
        <button className="btn-secondary text-sm" onClick={loadDetail}>
          {expanded ? "بستن" : "مشاهده پیام‌ها"}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 overflow-x-auto">
          {detailLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-400 p-2">
              <Spinner /> در حال دریافت پیام‌های صف…
            </div>
          ) : detailError ? (
            <div className="card text-sm border-red-500/50 bg-red-500/10 text-red-200 p-2">
              ⚠️ {detailError}
              <button className="btn-secondary text-xs mr-2" onClick={() => { setExpanded(false); loadDetail(); }}>
                تلاش مجدد
              </button>
            </div>
          ) : (!detail?.queue || detail.queue.length === 0) ? (
            <Empty label="صف خالی است." />
          ) : (
            <table className="w-full text-xs">
              <thead className="text-slate-400"><tr><th className="text-right p-1">نوع</th><th className="text-right p-1">متن</th></tr></thead>
              <tbody>
                {detail.queue.slice(0, 100).map((q, i) => (
                  <tr key={i} className="border-t border-slate-800">
                    <td className="p-1">{queueItemType(q)}</td>
                    <td className="p-1 text-slate-300">{queueItemText(q).slice(0, 80) || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {hasQueue && (
        <div className="mt-3 border-t border-slate-700 pt-3 space-y-2">
          <p className="text-xs text-red-300">
            ⚠️ تمام پیام‌های در صف حذف می‌شوند و ارسال نخواهند شد. برای توقف اضطراری یک کمپین اشتباه.
          </p>
          <div className="flex gap-2">
            <input className="input flex-1" placeholder="برای تأیید بنویسید: پاک کن" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
            <button className="btn-danger whitespace-nowrap" disabled={clearing || confirmText.trim() !== "پاک کن"} onClick={clearQueue}>
              🛑 خالی کردن صف
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
