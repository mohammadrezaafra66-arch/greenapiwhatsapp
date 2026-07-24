import React from "react";
import { OwnNumbersApi } from "../api.js";
import { toast, confirmDialog } from "../ui/toast.jsx";

// V45 PART 1 — «شماره‌های خودی (حذف از رصد)»: manage the list of our own numbers whose content is
// never counted as a product mention, never analyzed by AI, and never harvested as a lead.
export default function OwnNumbers() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [phone, setPhone] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setData(await OwnNumbersApi.list());
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    load();
  }, []);

  const add = async () => {
    if (!phone.trim()) return toast.error("شماره لازم است");
    setBusy(true);
    try {
      const res = await OwnNumbersApi.add(phone.trim(), label.trim() || null);
      toast.success(res.created ? "شماره اضافه شد" : "این شماره از قبل در فهرست است");
      setPhone("");
      setLabel("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    if (!(await confirmDialog("این شماره از فهرست خودی حذف شود؟"))) return;
    try {
      await OwnNumbersApi.remove(id);
      toast.success("حذف شد");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const reseed = async () => {
    try {
      const res = await OwnNumbersApi.reseed();
      toast.success(res.added > 0 ? `${res.added} شمارهٔ اینستنس اضافه شد` : "شمارهٔ جدیدی برای افزودن نبود");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const items = data?.items || [];

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h2 className="text-2xl font-bold">شماره‌های خودی (حذف از رصد محصولات)</h2>
        <p className="text-sm text-slate-400 mt-1">
          محتوای این شماره‌ها هرگز به‌عنوان «مشاهدهٔ محصول» در گزارش پرتکرار محصولات شمرده نمی‌شود،
          هرگز توکن هوش مصنوعی مصرف نمی‌کند و هرگز در فهرست «مخاطبین فعال واتساپ» ثبت نمی‌شود.
          شماره‌های اینستنس‌های متصل به‌صورت خودکار اینجا افزوده می‌شوند؛ می‌توانید شماره‌های دیگر
          (خطوط شخصی/کاری) را هم دستی اضافه کنید.
        </p>
      </div>

      <div className="card space-y-3">
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="label">شماره</label>
            <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)}
              placeholder="09121234567 یا 989121234567" />
          </div>
          <div>
            <label className="label">توضیح (اختیاری)</label>
            <input className="input" value={label} onChange={(e) => setLabel(e.target.value)}
              placeholder="مثلاً: خط پشتیبانی" />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-primary" disabled={busy} onClick={add}>{busy ? "..." : "افزودن شماره"}</button>
          <button className="btn-secondary" onClick={reseed}>🔄 همگام‌سازی از اینستنس‌ها</button>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm text-slate-400">
            فهرست شماره‌های خودی{data?.count != null ? ` · ${Number(data.count).toLocaleString("fa-IR")} مورد` : ""}
          </p>
          <button className="btn-secondary text-xs" disabled={loading} onClick={load}>
            {loading ? "..." : "🔄 تازه‌سازی"}
          </button>
        </div>

        {items.length === 0 ? (
          <p className="text-slate-500 text-sm">هنوز شماره‌ای در فهرست نیست.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-right">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="py-2 px-2">#</th>
                  <th className="py-2 px-2">شماره</th>
                  <th className="py-2 px-2">توضیح</th>
                  <th className="py-2 px-2">منبع</th>
                  <th className="py-2 px-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((r, i) => (
                  <tr key={r.id} className="border-b border-slate-800">
                    <td className="py-2 px-2 text-slate-500">{Number(i + 1).toLocaleString("fa-IR")}</td>
                    <td className="py-2 px-2 font-mono">{r.phone_raw || r.phone_core}</td>
                    <td className="py-2 px-2 text-slate-300">{r.label || "—"}</td>
                    <td className="py-2 px-2">
                      <span className={`badge text-xs ${r.source === "account" ? "bg-sky-500/20 text-sky-300 border-sky-500/40" : "bg-slate-500/20 text-slate-300 border-slate-500/40"}`}>
                        {r.source === "account" ? "اینستنس" : "دستی"}
                      </span>
                    </td>
                    <td className="py-2 px-2">
                      <button className="btn-secondary text-xs" onClick={() => remove(r.id)}>حذف</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
