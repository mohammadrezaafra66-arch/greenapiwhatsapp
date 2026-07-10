import React from "react";
import { StatusScheduleApi as Api, Accounts as AccApi, ProductsApi } from "../api.js";
import { Spinner, Empty, Modal } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

const STATUS_TYPES = [
  { v: "intro", l: "معرفی مجموعه" },
  { v: "special_offer", l: "پیشنهاد ویژه" },
  { v: "custom", l: "متن دلخواه" },
];
const INTRO_SUBTYPES = [
  { v: "history", l: "تاریخچه" },
  { v: "services", l: "خدمات" },
  { v: "differentiators", l: "تمایزها" },
  { v: "collaboration", l: "شیوه همکاری" },
  { v: "purchase", l: "شیوه خرید" },
  { v: "contact", l: "راه‌های ارتباطی" },
];
const CONTENT_TYPES = [
  { v: "text", l: "متنی" },
  { v: "text_price", l: "متنی با قیمت" },
  { v: "image", l: "عکس" },
  { v: "image_caption", l: "عکس با کپشن" },
];
const DAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];

const labelOf = (arr, v) => (arr.find((x) => x.v === v) || {}).l || v;

export default function StatusScheduler() {
  const [accounts, setAccounts] = React.useState([]);
  const [accLoading, setAccLoading] = React.useState(true);
  const [accountId, setAccountId] = React.useState("");
  const [list, setList] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [edit, setEdit] = React.useState(null); // null | {} (create) | schedule (edit)

  React.useEffect(() => {
    AccApi.list()
      .then((r) => {
        const arr = r || [];
        setAccounts(arr);
        if (arr.length) setAccountId(String(arr[0].id));
      })
      .catch((e) => setError(e?.response?.data?.detail || e.message))
      .finally(() => setAccLoading(false));
  }, []);

  const load = React.useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const r = await Api.list(id);
      setList(r || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setList([]);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (accountId) load(accountId);
  }, [accountId, load]);

  const toggle = async (s) => {
    try {
      await Api.toggle(s.id);
      await load(accountId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const remove = async (s) => {
    if (!(await confirmDialog("این برنامه استوری حذف شود؟"))) return;
    try {
      await Api.delete(s.id);
      toast.success("حذف شد");
      await load(accountId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const timingSummary = (s) => {
    const parts = [];
    const days = s.days_of_week || [];
    const dates = s.specific_dates || [];
    if (days.length) {
      parts.push("روزها: " + days.map((d) => DAYS[d] || d).join("،"));
    } else if (dates.length) {
      parts.push("تاریخ‌ها: " + dates.join("،"));
    }
    const times = s.times || [];
    if (times.length) parts.push("ساعت‌ها: " + times.join("،"));
    return parts.join(" · ") || "—";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">برنامه استوری</h2>
        <button className="btn-primary" onClick={() => setEdit({})}>+ برنامه جدید</button>
      </div>

      <div className="card text-sm text-slate-300 bg-sky-500/10 border-sky-500/30">
        استوری‌ها به‌صورت خودکار در روزها/ساعت‌های تعیین‌شده روی حساب انتخابی منتشر می‌شوند.
      </div>

      <div className="card">
        <label className="label">انتخاب حساب</label>
        {accLoading ? (
          <Spinner />
        ) : (
          <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">— یک حساب انتخاب کنید —</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        )}
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}

      {!loading && accountId && list.length === 0 && <Empty label="برنامه‌ای تنظیم نشده است." />}

      <div className="space-y-3">
        {list.map((s) => (
          <div key={s.id} className="card">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold">{s.name || labelOf(STATUS_TYPES, s.status_type)}</span>
                <span className="badge bg-slate-700 text-slate-300 border-slate-600">
                  {labelOf(STATUS_TYPES, s.status_type)}
                </span>
                <span className={`badge ${s.is_active ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-500/20 text-slate-300 border-slate-500/40"}`}>
                  {s.is_active ? "فعال" : "غیرفعال"}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn-secondary" onClick={() => setEdit(s)}>ویرایش</button>
                <button className="btn-secondary" onClick={() => toggle(s)}>
                  {s.is_active ? "غیرفعال" : "فعال"}
                </button>
                <button className="btn-danger" onClick={() => remove(s)}>حذف</button>
              </div>
            </div>
            <div className="text-sm text-slate-400">{timingSummary(s)}</div>
            <div className="text-xs text-slate-500 mt-1">
              اجرای بعدی: {s.next_run_shamsi || "—"}
              {s.last_run_shamsi ? ` · اجرای قبلی: ${s.last_run_shamsi}` : ""}
            </div>
          </div>
        ))}
      </div>

      {edit && (
        <ScheduleModal
          schedule={edit}
          accounts={accounts}
          defaultAccountId={accountId}
          onClose={() => setEdit(null)}
          onDone={() => load(accountId)}
        />
      )}
    </div>
  );
}

function seedForm(s, defaultAccountId) {
  return {
    account_id: s.account_id ? String(s.account_id) : (defaultAccountId || ""),
    name: s.name || "",
    status_type: s.status_type || "intro",
    content_type: s.content_type || "text",
    intro_subtype: s.intro_subtype || "history",
    custom_text: s.custom_text || "",
    show_price: s.show_price ?? false,
    include_image: s.include_image ?? false,
    include_caption: s.include_caption ?? false,
    image_url: s.image_url || "",
    product_selection: s.product_selection || "manual",
    product_pool: Array.isArray(s.product_pool) ? s.product_pool : [],
    product_pick_count: s.product_pick_count ?? 3,
    days_of_week: Array.isArray(s.days_of_week) ? s.days_of_week : [],
    specific_dates: Array.isArray(s.specific_dates) ? s.specific_dates : [],
    times: Array.isArray(s.times) ? s.times : [],
    is_active: s.is_active !== undefined ? s.is_active : true,
  };
}

function ScheduleModal({ schedule, accounts, defaultAccountId, onClose, onDone }) {
  const isEdit = !!schedule.id;
  const [f, setF] = React.useState(() => seedForm(schedule, defaultAccountId));
  const [saving, setSaving] = React.useState(false);
  const [products, setProducts] = React.useState([]);
  const [prodLoading, setProdLoading] = React.useState(false);
  const [timeInput, setTimeInput] = React.useState("");
  const [dateInput, setDateInput] = React.useState("");

  const set = (k) => (e) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  // Fetch products only when needed (special_offer + manual)
  React.useEffect(() => {
    if (f.status_type === "special_offer" && products.length === 0) {
      setProdLoading(true);
      ProductsApi.list()
        .then((r) => {
          const flat = [];
          (r || []).forEach((grp) => {
            (grp.products || []).forEach((p) => {
              if (p && p.name) flat.push(p.name);
            });
          });
          setProducts(Array.from(new Set(flat)));
        })
        .catch(() => setProducts([]))
        .finally(() => setProdLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.status_type]);

  const toggleDay = (idx) => {
    const days = f.days_of_week || [];
    setF({
      ...f,
      days_of_week: days.includes(idx) ? days.filter((d) => d !== idx) : [...days, idx].sort((a, b) => a - b),
    });
  };

  const toggleProduct = (name) => {
    const pool = f.product_pool || [];
    setF({
      ...f,
      product_pool: pool.includes(name) ? pool.filter((p) => p !== name) : [...pool, name],
    });
  };

  const addTime = () => {
    const v = (timeInput || "").trim();
    if (!v) return;
    if ((f.times || []).includes(v)) return setTimeInput("");
    setF({ ...f, times: [...(f.times || []), v] });
    setTimeInput("");
  };
  const removeTime = (t) => setF({ ...f, times: (f.times || []).filter((x) => x !== t) });

  const addDate = () => {
    const v = (dateInput || "").trim();
    if (!v) return;
    if ((f.specific_dates || []).includes(v)) return setDateInput("");
    setF({ ...f, specific_dates: [...(f.specific_dates || []), v] });
    setDateInput("");
  };
  const removeDate = (d) => setF({ ...f, specific_dates: (f.specific_dates || []).filter((x) => x !== d) });

  const submit = async () => {
    if (!f.account_id) return toast.error("لطفاً حساب را انتخاب کنید");
    if ((f.times || []).length === 0) return toast.error("حداقل یک ساعت اضافه کنید");
    if (f.status_type === "custom" && !f.custom_text.trim())
      return toast.error("لطفاً متن دلخواه را وارد کنید");

    setSaving(true);
    try {
      const body = {
        account_id: f.account_id,
        name: f.name || null,
        status_type: f.status_type,
        content_type: f.content_type,
        intro_subtype: f.intro_subtype,
        custom_text: f.custom_text || null,
        show_price: !!f.show_price,
        include_image: f.content_type === "image" || f.content_type === "image_caption",
        include_caption: !!f.include_caption,
        image_url: f.image_url || null,
        product_selection: f.product_selection,
        product_pool: f.product_pool || [],
        product_pick_count: Number(f.product_pick_count) || 3,
        days_of_week: f.days_of_week || [],
        specific_dates: f.specific_dates || [],
        times: f.times || [],
        is_active: !!f.is_active,
      };
      if (isEdit) await Api.update(schedule.id, body);
      else await Api.create(body);
      toast.success("ذخیره شد");
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const isImage = f.content_type === "image" || f.content_type === "image_caption";

  return (
    <Modal title={isEdit ? "ویرایش برنامه استوری" : "برنامه استوری جدید"} onClose={onClose} wide>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">حساب</label>
            <select className="input" value={f.account_id} onChange={set("account_id")}>
              <option value="">— انتخاب حساب —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">نام (اختیاری)</label>
            <input className="input" value={f.name} onChange={set("name")} />
          </div>
        </div>

        <div>
          <label className="label">نوع استوری</label>
          <select className="input" value={f.status_type} onChange={set("status_type")}>
            {STATUS_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
          </select>
        </div>

        {f.status_type === "intro" && (
          <div>
            <label className="label">زیرنوع</label>
            <select className="input" value={f.intro_subtype} onChange={set("intro_subtype")}>
              {INTRO_SUBTYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
            </select>
          </div>
        )}

        {f.status_type === "special_offer" && (
          <div className="rounded-lg border border-slate-700 p-3 space-y-3">
            <p className="font-bold text-sm">پیشنهاد ویژه</p>
            <div>
              <label className="label">انتخاب محصول</label>
              <select className="input" value={f.product_selection} onChange={set("product_selection")}>
                <option value="manual">دستی</option>
                <option value="random">رندوم</option>
              </select>
            </div>

            {f.product_selection === "manual" && (
              <div>
                <label className="label">
                  انتخاب محصولات ({fa((f.product_pool || []).length)} انتخاب‌شده)
                </label>
                {prodLoading ? (
                  <Spinner />
                ) : products.length === 0 ? (
                  <Empty label="محصولی یافت نشد." />
                ) : (
                  <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-700 p-2 space-y-1">
                    {products.map((name) => (
                      <label key={name} className="flex items-center gap-2 text-sm py-0.5">
                        <input
                          type="checkbox"
                          checked={(f.product_pool || []).includes(name)}
                          onChange={() => toggleProduct(name)}
                        />
                        <span className="text-slate-300">{name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div>
              <label className="label">تعداد انتخاب در هر بار</label>
              <input
                type="number"
                min={1}
                className="input"
                value={f.product_pick_count}
                onChange={set("product_pick_count")}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={f.show_price} onChange={set("show_price")} />
              نمایش قیمت
            </label>
          </div>
        )}

        {f.status_type === "custom" && (
          <div>
            <label className="label">متن دلخواه</label>
            <textarea className="input h-24" value={f.custom_text} onChange={set("custom_text")} />
          </div>
        )}

        <div>
          <label className="label">نوع محتوا</label>
          <select className="input" value={f.content_type} onChange={set("content_type")}>
            {CONTENT_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
          </select>
        </div>

        {isImage && (
          <div className="rounded-lg border border-slate-700 p-3 space-y-2">
            <div>
              <label className="label">آدرس تصویر</label>
              <input className="input" dir="ltr" value={f.image_url} onChange={set("image_url")} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={f.include_caption} onChange={set("include_caption")} />
              کپشن
            </label>
          </div>
        )}

        <div className="border-t border-slate-700 pt-3 mt-3 space-y-3">
          <p className="font-bold text-sm">زمان‌بندی</p>

          <div>
            <label className="label">روزهای هفته</label>
            <div className="flex flex-wrap gap-2">
              {DAYS.map((d, idx) => (
                <button
                  key={idx}
                  type="button"
                  className={(f.days_of_week || []).includes(idx) ? "btn-primary" : "btn-secondary"}
                  onClick={() => toggleDay(idx)}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="label">ساعت‌ها</label>
            <div className="flex gap-2">
              <input
                type="time"
                className="input flex-1"
                value={timeInput}
                onChange={(e) => setTimeInput(e.target.value)}
              />
              <button type="button" className="btn-secondary whitespace-nowrap" onClick={addTime}>
                افزودن ساعت
              </button>
            </div>
            {(f.times || []).length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {f.times.map((t) => (
                  <span
                    key={t}
                    className="badge bg-slate-700 text-slate-300 border-slate-600 flex items-center gap-1"
                  >
                    {t}
                    <button
                      type="button"
                      className="text-red-400 hover:text-red-300"
                      onClick={() => removeTime(t)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="label">یا تاریخ‌های مشخص (شمسی، مثال ۱۴۰۳/۰۵/۲۰)</label>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                dir="ltr"
                value={dateInput}
                onChange={(e) => setDateInput(e.target.value)}
                placeholder="۱۴۰۳/۰۵/۲۰"
              />
              <button type="button" className="btn-secondary whitespace-nowrap" onClick={addDate}>
                افزودن تاریخ
              </button>
            </div>
            {(f.specific_dates || []).length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {f.specific_dates.map((d) => (
                  <span
                    key={d}
                    className="badge bg-slate-700 text-slate-300 border-slate-600 flex items-center gap-1"
                  >
                    {d}
                    <button
                      type="button"
                      className="text-red-400 hover:text-red-300"
                      onClick={() => removeDate(d)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.is_active} onChange={set("is_active")} />
          فعال
        </label>

        <button className="btn-primary w-full" disabled={saving} onClick={submit}>
          {saving ? "در حال ذخیره..." : isEdit ? "ذخیره تغییرات" : "ساخت برنامه"}
        </button>
      </div>
    </Modal>
  );
}
