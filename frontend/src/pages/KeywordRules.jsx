import React from "react";
import { KeywordRulesApi as Api } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const MATCH_FA = { exact: "دقیق", contains: "شامل" };
const SCOPE_FA = { pv: "خصوصی", group: "گروه", both: "هر دو" };

export default function KeywordRules() {
  const { data, loading, error, reload } = useAsync(() => Api.list(), []);
  const [edit, setEdit] = React.useState(null); // null | {} (new) | rule (edit)

  const remove = async (id) => {
    if (!(await confirmDialog("حذف قانون؟"))) return;
    try {
      await Api.delete(id);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">قوانین پاسخ خودکار</h2>
        <button className="btn-primary" onClick={() => setEdit({})}>+ افزودن قانون</button>
      </div>

      <div className="card text-sm bg-sky-50 text-sky-700 border-sky-200">
        هر پیام ورودی با این کلیدواژه‌ها بررسی می‌شود. اولین تطابق پاسخ می‌دهد.
      </div>

      {loading && <Spinner />}
      {error && <div className="card bg-red-50 text-red-700 border-red-200">{error}</div>}
      {data && data.length === 0 && <Empty label="قانونی وجود ندارد." />}

      {data && data.length > 0 && (
        <div className="card table-wrap">
          <table className="table w-full text-sm">
            <thead>
              <tr className="text-muted border-b border-line">
                <th className="text-right p-2">کلیدواژه</th>
                <th className="text-right p-2">پاسخ</th>
                <th className="text-right p-2">نوع تطبیق</th>
                <th className="text-right p-2">حوزه</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">تعداد استفاده</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="border-b border-line">
                  <td className="p-2 font-bold">{r.keyword}</td>
                  <td className="p-2 text-muted">
                    {(r.reply_message || "").slice(0, 60)}
                    {(r.reply_message || "").length > 60 ? "…" : ""}
                  </td>
                  <td className="p-2">{MATCH_FA[r.match_type] || r.match_type}</td>
                  <td className="p-2">{SCOPE_FA[r.scope] || r.scope}</td>
                  <td className="p-2">
                    <span className={`badge ${r.is_active ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`}>
                      {r.is_active ? "فعال" : "غیرفعال"}
                    </span>
                  </td>
                  <td className="p-2">{r.use_count}</td>
                  <td className="p-2">
                    <div className="flex gap-2">
                      <button className="btn-secondary btn-sm" onClick={() => setEdit(r)}>ویرایش</button>
                      <button className="btn-danger btn-sm" onClick={() => remove(r.id)}>حذف</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {edit && <RuleModal rule={edit} onClose={() => setEdit(null)} onDone={reload} />}
    </div>
  );
}

function RuleModal({ rule, onClose, onDone }) {
  const isEdit = !!rule.id;
  const [f, setF] = React.useState({
    keyword: rule.keyword || "",
    reply_message: rule.reply_message || "",
    match_type: rule.match_type || "contains",
    scope: rule.scope || "both",
    is_active: rule.is_active !== undefined ? rule.is_active : true,
  });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const submit = async () => {
    if (!f.keyword || !f.reply_message) return toast.error("کلیدواژه و متن پاسخ لازم است");
    setSaving(true);
    try {
      const body = {
        keyword: f.keyword,
        reply_message: f.reply_message,
        match_type: f.match_type,
        scope: f.scope,
        is_active: f.is_active,
      };
      if (isEdit) await Api.update(rule.id, body);
      else await Api.create(body);
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={isEdit ? "ویرایش قانون" : "قانون جدید"} onClose={onClose}>
      <div className="space-y-3">
        <div><label className="label">کلیدواژه</label><input className="input" value={f.keyword} onChange={set("keyword")} /></div>
        <div><label className="label">متن پاسخ</label><textarea className="input h-24" value={f.reply_message} onChange={set("reply_message")} /></div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="label">نوع تطبیق</label>
            <select className="input" value={f.match_type} onChange={set("match_type")}>
              <option value="contains">شامل</option>
              <option value="exact">دقیق</option>
            </select>
            <p className="text-xs text-muted mt-1">دقیق = پیام باید عیناً همان کلیدواژه باشد | شامل = پیام حاوی کلیدواژه باشد</p>
          </div>
          <div>
            <label className="label">حوزه</label>
            <select className="input" value={f.scope} onChange={set("scope")}>
              <option value="both">هر دو</option>
              <option value="pv">خصوصی</option>
              <option value="group">گروه</option>
            </select>
            <p className="text-xs text-muted mt-1">خصوصی = فقط پیام‌های مستقیم | گروه = فقط پیام‌های گروهی | هر دو = همه پیام‌ها</p>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.is_active} onChange={set("is_active")} />
          فعال
        </label>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "..." : "ذخیره"}</button>
      </div>
    </Modal>
  );
}
