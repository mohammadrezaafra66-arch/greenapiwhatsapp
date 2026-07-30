import React from "react";
import { MessagesApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

// FEATURE 8 — CRUD for button auto-replies: when a recipient presses a button
// (matched by buttonId OR exact buttonText), reply automatically with reply_text.
export default function ButtonAutoReplies() {
  const { data, loading, reload } = useAsync(() => MessagesApi.autoReplies(), []);
  const [f, setF] = React.useState({ button_id: "", button_text: "", reply_text: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function add() {
    if (!f.reply_text.trim()) return toast.error("متن پاسخ لازم است");
    if (!f.button_id.trim() && !f.button_text.trim()) return toast.error("شناسه دکمه یا متن دکمه لازم است");
    try {
      await MessagesApi.createAutoReply(f);
      toast.success("قانون افزوده شد");
      setF({ button_id: "", button_text: "", reply_text: "" });
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function toggle(r) {
    await MessagesApi.updateAutoReply(r.id, { ...r, enabled: !r.enabled });
    reload();
  }
  async function del(id) {
    if (!(await confirmDialog("این قانون حذف شود؟"))) return;
    await MessagesApi.deleteAutoReply(id); reload();
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">پاسخ خودکار دکمه‌ها</h2>
      <p className="text-sm text-muted">
        وقتی مخاطبی روی یک دکمه تعاملی می‌زند، سامانه بر اساس شناسه دکمه یا متن دقیق دکمه، پاسخ تعیین‌شده را می‌فرستد.
      </p>

      <div className="card space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <input className="input" placeholder="شناسه دکمه (مثلاً 1)" value={f.button_id} onChange={set("button_id")} />
          <input className="input" placeholder="یا متن دقیق دکمه (مثلاً قیمت)" value={f.button_text} onChange={set("button_text")} />
        </div>
        <textarea className="input h-20" placeholder="متن پاسخ خودکار..." value={f.reply_text} onChange={set("reply_text")} />
        <button className="btn-primary w-full sm:w-auto" onClick={add}>افزودن قانون</button>
      </div>

      {loading ? <Spinner /> : (!data || data.length === 0) ? <Empty label="قانونی ثبت نشده." /> : (
        <div className="card table-wrap">
          <table className="w-full text-sm">
            <thead className="text-muted text-xs">
              <tr>
                <th className="text-right p-2">شناسه دکمه</th>
                <th className="text-right p-2">متن دکمه</th>
                <th className="text-right p-2">پاسخ</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">اقدامات</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="border-t border-line">
                  <td className="p-2 font-mono">{r.button_id || "—"}</td>
                  <td className="p-2">{r.button_text || "—"}</td>
                  <td className="p-2 text-ink">{r.reply_text}</td>
                  <td className="p-2">
                    <button className={`badge ${r.enabled ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`} onClick={() => toggle(r)}>
                      {r.enabled ? "فعال" : "غیرفعال"}
                    </button>
                  </td>
                  <td className="p-2"><button className="btn-danger btn-sm" onClick={() => del(r.id)}>حذف</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
