import React from "react";
import { AccountSchedulesApi as Api, Accounts, PresetsApi } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

export default function AccountSchedules() {
  const { data: accounts, loading: accLoading } = useAsync(() => Accounts.list(), []);
  const [accountId, setAccountId] = React.useState("");
  const [sched, setSched] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [edit, setEdit] = React.useState(null); // null | {} | slot
  const [delay, setDelayState] = React.useState({ min_delay_seconds: 45, max_delay_seconds: 110 });
  const [savingDelay, setSavingDelay] = React.useState(false);

  const load = React.useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const r = await Api.get(id);
      setSched(r);
      setDelayState(r.delay || { min_delay_seconds: 45, max_delay_seconds: 110 });
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setSched(null);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (accountId) load(accountId);
  }, [accountId, load]);

  const saveDelay = async () => {
    setSavingDelay(true);
    try {
      await Api.updateDelay(accountId, {
        min_delay_seconds: Number(delay.min_delay_seconds),
        max_delay_seconds: Number(delay.max_delay_seconds),
      });
      toast.success("تأخیر ذخیره شد");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSavingDelay(false);
    }
  };

  const removeSlot = async (id) => {
    if (!(await confirmDialog("حذف بازه؟"))) return;
    try {
      await Api.deleteSlot(id);
      await load(accountId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">زمان‌بندی ارسال</h2>
        {accountId && <button className="btn-primary" onClick={() => setEdit({})}>+ افزودن بازه</button>}
      </div>

      <div className="card text-sm text-slate-300 bg-sky-500/10 border-sky-500/30">
        بازه‌های زمانی که اینجا تعریف می‌کنید جایگزین زمان‌بندی پیش‌فرض سیستم می‌شوند. ساعت‌هایی که بازه تعریف نشده باشد، ارسال متوقف می‌ماند.
      </div>

      <div className="card">
        <label className="label">انتخاب حساب</label>
        {accLoading ? (
          <Spinner />
        ) : (
          <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">— یک حساب انتخاب کنید —</option>
            {accounts?.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        )}
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}

      {accountId && sched && (
        <>
          <div className="card space-y-3">
            <h3 className="font-bold">تأخیر ارسال (ثانیه)</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">حداقل</label>
                <input type="number" className="input" value={delay.min_delay_seconds}
                  onChange={(e) => setDelayState({ ...delay, min_delay_seconds: e.target.value })} />
              </div>
              <div>
                <label className="label">حداکثر</label>
                <input type="number" className="input" value={delay.max_delay_seconds}
                  onChange={(e) => setDelayState({ ...delay, max_delay_seconds: e.target.value })} />
              </div>
            </div>
            <button className="btn-primary" disabled={savingDelay} onClick={saveDelay}>
              {savingDelay ? "..." : "ذخیره تأخیر"}
            </button>
          </div>

          <div className="card overflow-x-auto">
            <h3 className="font-bold mb-3">بازه‌های ساعتی</h3>
            {sched.schedule.length === 0 ? (
              <Empty label="بازه‌ای تعریف نشده است." />
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 border-b border-slate-700">
                    <th className="text-right p-2">از ساعت</th>
                    <th className="text-right p-2">تا ساعت</th>
                    <th className="text-right p-2">حداکثر ارسال در ساعت</th>
                    <th className="text-right p-2">توضیح برای هوش مصنوعی</th>
                    <th className="text-right p-2">قالب</th>
                    <th className="text-right p-2">وضعیت</th>
                    <th className="text-right p-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {sched.schedule.map((s) => (
                    <tr key={s.id} className="border-b border-slate-800">
                      <td className="p-2">{s.hour_start}</td>
                      <td className="p-2">{s.hour_end}</td>
                      <td className="p-2">{s.max_per_hour}</td>
                      <td className="p-2 text-slate-300">
                        {(s.gpt_prompt || "").slice(0, 50)}{(s.gpt_prompt || "").length > 50 ? "…" : ""}
                        {s.include_products && (
                          <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40 mr-1">🛒 محصولات</span>
                        )}
                      </td>
                      <td className="p-2 text-slate-300">{(s.message_template || "").slice(0, 30)}{(s.message_template || "").length > 30 ? "…" : ""}</td>
                      <td className="p-2">
                        <span className={`badge ${s.is_active ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-500/20 text-slate-300 border-slate-500/40"}`}>
                          {s.is_active ? "فعال" : "غیرفعال"}
                        </span>
                      </td>
                      <td className="p-2">
                        <div className="flex gap-2">
                          <button className="text-sky-400 hover:underline" onClick={() => setEdit(s)}>ویرایش</button>
                          <button className="text-red-400 hover:underline" onClick={() => removeSlot(s.id)}>حذف</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {edit && (
        <SlotModal
          slot={edit}
          accountId={accountId}
          onClose={() => setEdit(null)}
          onDone={() => load(accountId)}
        />
      )}
    </div>
  );
}

function SlotModal({ slot, accountId, onClose, onDone }) {
  const isEdit = !!slot.id;
  const [f, setF] = React.useState({
    hour_start: slot.hour_start ?? 8,
    hour_end: slot.hour_end ?? 22,
    max_per_hour: slot.max_per_hour ?? 0,
    gpt_prompt: slot.gpt_prompt || "",
    message_template: slot.message_template || "",
    is_active: slot.is_active !== undefined ? slot.is_active : true,
    include_products: slot.include_products ?? false,
  });
  const [saving, setSaving] = React.useState(false);
  const [presets, setPresets] = React.useState([]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  React.useEffect(() => {
    PresetsApi.list().then((r) => setPresets(r || [])).catch(() => setPresets([]));
  }, []);

  const submit = async () => {
    setSaving(true);
    try {
      const body = {
        account_id: accountId,
        hour_start: Number(f.hour_start),
        hour_end: Number(f.hour_end),
        max_per_hour: Number(f.max_per_hour),
        gpt_prompt: f.gpt_prompt || null,
        message_template: f.message_template || null,
        is_active: f.is_active,
        include_products: f.include_products,
      };
      if (isEdit) await Api.updateSlot(slot.id, body);
      else await Api.createSlot(body);
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={isEdit ? "ویرایش بازه" : "بازه جدید"} onClose={onClose}>
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-3">
          <div><label className="label">از ساعت</label><input type="number" min="0" max="23" className="input" value={f.hour_start} onChange={set("hour_start")} /></div>
          <div><label className="label">تا ساعت</label><input type="number" min="1" max="24" className="input" value={f.hour_end} onChange={set("hour_end")} /></div>
          <div><label className="label">حداکثر/ساعت</label><input type="number" min="0" className="input" value={f.max_per_hour} onChange={set("max_per_hour")} /></div>
        </div>
        <p className="text-xs text-slate-500 -mt-1">(ساعت تهران، ۰ تا ۲۳)</p>

        {presets.length > 0 && (
          <div className="space-y-2">
            <label className="label">پیش‌نویس‌های آماده</label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {presets.map((p) => {
                const selected = f.gpt_prompt && f.gpt_prompt === p.gpt_prompt;
                return (
                  <div
                    key={p.key}
                    onClick={() => setF({ ...f, gpt_prompt: p.gpt_prompt })}
                    className={`card cursor-pointer hover:border-emerald-500/50 transition ${selected ? "border-emerald-500 ring-1 ring-emerald-500" : ""}`}
                  >
                    <div className="font-bold text-sm">{p.label}</div>
                    <div className="text-xs text-slate-400 mt-1">{p.example}</div>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-slate-500">
              💡 مثال: ساعت ۸-۹ پیش‌نویس «صبح‌بخیر» → پیام انگیزشی؛ ساعت ۱۱-۱۲ پیش‌نویس «محصولات با قیمت» + تیک «افزودن محصولات» → قیمت لحظه‌ای درج می‌شود.
            </p>
          </div>
        )}

        <div><label className="label">توضیح برای هوش مصنوعی (اختیاری)</label><textarea className="input h-20" value={f.gpt_prompt} onChange={set("gpt_prompt")} /></div>
        <div><label className="label">قالب پیام (اختیاری)</label><textarea className="input h-20" value={f.message_template} onChange={set("message_template")} /></div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.include_products} onChange={set("include_products")} />
          افزودن محصولات به پیام
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.is_active} onChange={set("is_active")} />
          فعال
        </label>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "..." : "ذخیره"}</button>
      </div>
    </Modal>
  );
}
