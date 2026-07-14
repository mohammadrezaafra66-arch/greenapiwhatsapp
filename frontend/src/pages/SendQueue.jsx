import React from "react";
import { QueueApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import { toast } from "../ui/toast.jsx";

const fa = (n) => (n == null ? "" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

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
  const [confirmText, setConfirmText] = React.useState("");
  const [clearing, setClearing] = React.useState(false);
  const hasQueue = (acc.count || 0) > 0;

  async function loadDetail() {
    if (!expanded) {
      try { setDetail(await QueueApi.get(acc.account_id)); } catch { /* ignore */ }
    }
    setExpanded((e) => !e);
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
          {(!detail?.queue || detail.queue.length === 0) ? (
            <Empty label="صف خالی است." />
          ) : (
            <table className="w-full text-xs">
              <thead className="text-slate-400"><tr><th className="text-right p-1">نوع</th><th className="text-right p-1">متن</th></tr></thead>
              <tbody>
                {detail.queue.slice(0, 100).map((q, i) => (
                  <tr key={i} className="border-t border-slate-800">
                    <td className="p-1">{q.type || q.typeMessage || "—"}</td>
                    <td className="p-1 text-slate-300">{(q.body || q.text || "").slice(0, 80) || "—"}</td>
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
