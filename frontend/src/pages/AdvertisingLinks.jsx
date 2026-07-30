import React from "react";
import { AdLinksApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const TYPE_FA = { telegram: "تلگرام", whatsapp: "واتساپ", instagram: "اینستاگرام", website: "وب‌سایت", other: "سایر" };
const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const BLANK = { url: "", title: "", link_type: "telegram", weight: 5, is_active: true };

// V16 PART 3 — «لینک‌های تبلیغاتی»: manage promo links appended to campaign messages.
export default function AdvertisingLinks() {
  const { data, loading, reload } = useAsync(() => AdLinksApi.list(), []);
  const [f, setF] = React.useState(BLANK);
  const [editId, setEditId] = React.useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function save() {
    if (!/^https?:\/\/.+/i.test(f.url.trim())) return toast.error("آدرس باید با http:// یا https:// شروع شود");
    if (!f.title.trim()) return toast.error("عنوان لازم است");
    const body = { ...f, weight: Number(f.weight) || 5 };
    try {
      if (editId) { await AdLinksApi.update(editId, body); toast.success("ذخیره شد"); }
      else { await AdLinksApi.create(body); toast.success("لینک افزوده شد"); }
      setF(BLANK); setEditId(null); reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  function edit(l) { setEditId(l.id); setF({ url: l.url, title: l.title, link_type: l.link_type, weight: l.weight, is_active: l.is_active }); }
  async function del(id) { if (await confirmDialog("این لینک حذف شود؟")) { await AdLinksApi.remove(id); reload(); } }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">لینک‌های تبلیغاتی</h2>
      <p className="text-sm text-muted">لینک‌های خود را ذخیره کنید تا در انتهای پیام‌های کمپین (به‌صورت ثابت یا رندوم وزنی) اضافه شوند.</p>

      <div className="card space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <input className="input" placeholder="آدرس (https://…)" value={f.url} onChange={set("url")} dir="ltr" />
          <input className="input" placeholder="عنوان فارسی (مثلاً کانال تلگرام)" value={f.title} onChange={set("title")} />
          <select className="input" value={f.link_type} onChange={set("link_type")}>
            {Object.entries(TYPE_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <div className="flex items-center gap-2">
            <label className="label mb-0 whitespace-nowrap">وزن (۱ تا ۱۰): {fa(f.weight)}</label>
            <input type="range" min={1} max={10} value={f.weight} onChange={set("weight")} className="flex-1" />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.is_active} onChange={set("is_active")} /> فعال
        </label>
        <div className="flex gap-2">
          <button className="btn-primary btn-md" onClick={save}>{editId ? "ذخیره تغییرات" : "افزودن لینک"}</button>
          {editId && <button className="btn-secondary btn-md" onClick={() => { setEditId(null); setF(BLANK); }}>انصراف</button>}
        </div>
      </div>

      {loading ? <Spinner /> : (!data || data.length === 0) ? <Empty label="لینکی ثبت نشده." /> : (
        <div className="card table-wrap">
          <table className="w-full text-sm">
            <thead className="text-muted text-xs">
              <tr>
                <th className="text-right p-2">عنوان</th>
                <th className="text-right p-2">آدرس</th>
                <th className="text-right p-2">نوع</th>
                <th className="text-right p-2">وزن</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">اقدامات</th>
              </tr>
            </thead>
            <tbody>
              {data.map((l) => (
                <tr key={l.id} className="border-t border-line">
                  <td className="p-2">{l.title}</td>
                  <td className="p-2 font-mono text-xs" dir="ltr"><a href={l.url} target="_blank" rel="noreferrer" className="text-sky-700 underline">{l.url}</a></td>
                  <td className="p-2">{TYPE_FA[l.link_type] || l.link_type}</td>
                  <td className="p-2">{fa(l.weight)}</td>
                  <td className="p-2">
                    <button className={`badge ${l.is_active ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`}
                      onClick={async () => { await AdLinksApi.toggle(l.id); reload(); }}>
                      {l.is_active ? "فعال" : "غیرفعال"}
                    </button>
                  </td>
                  <td className="p-2">
                    <div className="flex gap-1">
                      <button className="btn-secondary btn-sm" onClick={() => edit(l)}>ویرایش</button>
                      <button className="btn-danger btn-sm" onClick={() => del(l.id)}>حذف</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
