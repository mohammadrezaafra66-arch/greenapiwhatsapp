import React from "react";
import { Campaigns as Api, FilesApi, Accounts, ContactGroupsApi, WaCollectionsApi, LabelsApi } from "../api.js";
import { Badge, Spinner, Empty, Modal, Progress, useAsync } from "../ui.jsx";

const TYPE_FA = {
  text: "متنی",
  image: "تصویری",
  poll: "نظرسنجی",
  interactive_buttons: "دکمه‌ای",
  status: "استوری",
};

export default function Campaigns() {
  const { data, loading, error, reload } = useAsync(Api.list, []);
  const [showAdd, setShowAdd] = React.useState(false);
  const [test, setTest] = React.useState(null);
  const [edit, setEdit] = React.useState(null); // { editId, initial }
  const [editLoading, setEditLoading] = React.useState(false);

  const act = async (fn) => {
    try {
      await fn();
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  const openEdit = async (c) => {
    setEditLoading(true);
    try {
      const detail = await Api.get(c.id);
      setEdit({ editId: c.id, initial: detail });
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setEditLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">گروه‌های پیام</h2>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>+ گروه پیام جدید</button>
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="گروه پیامی وجود ندارد." />}

      <div className="space-y-3">
        {data?.map((c) => (
          <div key={c.id} className="card">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <div className="flex items-center gap-2">
                <span className="font-bold">{c.name}</span>
                <Badge status={c.status} />
                <span className="badge bg-slate-700 text-slate-300 border-slate-600">{TYPE_FA[c.campaign_type] || c.campaign_type}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {c.status === "running" ? (
                  <button className="btn-secondary" onClick={() => act(() => Api.pause(c.id))}>توقف</button>
                ) : (
                  <button className="btn-primary" onClick={() => act(() => (c.status === "paused" ? Api.resume(c.id) : Api.start(c.id)))}>شروع</button>
                )}
                <button className="btn-secondary" onClick={() => setTest(c)}>تست</button>
                <button className="btn-secondary" disabled={editLoading} onClick={() => openEdit(c)}>✏️ ویرایش</button>
                <button className="btn-secondary" onClick={() => act(() => Api.toggleActive(c.id))}>
                  {c.is_active ? "⏸️ غیرفعال" : "▶️ فعال"}
                </button>
                <button className="btn-danger" onClick={() => { if (confirm("این گروه پیام حذف شود؟")) act(() => Api.remove(c.id)); }}>حذف</button>
              </div>
            </div>
            <div className="flex justify-between text-sm mb-1 text-slate-400">
              <span>پیشرفت: {c.sent_count} / {c.total_contacts}</span>
              <span>تحویل: {c.delivered_count} · خوانده: {c.read_count} · ناموفق: {c.failed_count}</span>
            </div>
            <Progress value={c.sent_count} max={c.total_contacts} />
            {(c.status === "running" || c.status === "paused") && <LiveLog campaignId={c.id} />}
          </div>
        ))}
      </div>

      {showAdd && <AddCampaignModal onClose={() => setShowAdd(false)} onDone={reload} />}
      {edit && (
        <AddCampaignModal
          editId={edit.editId}
          initial={edit.initial}
          onClose={() => setEdit(null)}
          onDone={reload}
        />
      )}
      {test && <TestModal campaign={test} onClose={() => setTest(null)} />}
    </div>
  );
}

function LiveLog({ campaignId }) {
  const [prog, setProg] = React.useState(null);
  const [failed, setFailed] = React.useState([]);
  const [err, setErr] = React.useState(null);
  const [tick, setTick] = React.useState(null);

  React.useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const [p, f] = await Promise.all([
          Api.progress(campaignId),
          Api.contacts(campaignId, "failed"),
        ]);
        if (!alive) return;
        setProg(p);
        setFailed(f);
        setErr(null);
        setTick(new Date());
      } catch (e) {
        if (alive) setErr(e?.response?.data?.detail || e.message);
      }
    };
    poll();
    const t = setInterval(poll, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [campaignId]);

  return (
    <div className="mt-3 rounded-lg bg-slate-900 border border-slate-700 p-3 text-sm space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-bold text-slate-300">گزارش زنده</span>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          {tick ? `به‌روزرسانی: ${tick.toLocaleTimeString("fa-IR")}` : "در حال اتصال..."}
        </span>
      </div>

      {err && <div className="text-red-400 text-xs">خطا در دریافت گزارش: {err}</div>}

      {prog?.pause_reason && (
        <div className="rounded bg-amber-500/10 border border-amber-500/40 text-amber-300 p-2 text-xs">
          ⏸️ {prog.pause_reason}
        </div>
      )}

      {prog && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="badge bg-slate-700 text-slate-300 border-slate-600">وضعیت: {prog.status}</span>
          <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">در انتظار: {prog.pending}</span>
          <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">ارسال‌شده: {prog.sent}</span>
          <span className="badge bg-red-500/20 text-red-300 border-red-500/40">ناموفق: {prog.failed}</span>
          <span className="badge bg-sky-500/20 text-sky-300 border-sky-500/40">پیشرفت: {prog.progress_pct}%</span>
        </div>
      )}

      {failed.length === 0 ? (
        <p className="text-xs text-slate-500">هیچ خطای ارسالی ثبت نشده است.</p>
      ) : (
        <div className="space-y-1 max-h-52 overflow-y-auto">
          <p className="text-xs text-red-300 font-bold">پیام‌های خطا ({failed.length}):</p>
          {failed.map((f) => (
            <div key={f.id} className="rounded bg-red-500/10 border border-red-500/30 p-2 text-xs">
              <div className="flex justify-between text-slate-400">
                <span className="font-mono">{f.phone}</span>
                <span>تلاش: {f.retry_count}</span>
              </div>
              <div className="text-red-300 mt-1 break-words whitespace-pre-wrap font-mono">
                {f.error_message || "بدون پیام خطا"}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const EMOJI_LEVELS = [
  { code: "none", label: "بدون ایموجی" },
  { code: "low", label: "کم" },
  { code: "medium", label: "متوسط" },
  { code: "high", label: "زیاد" },
];

const CAMPAIGN_DEFAULTS = {
  name: "", campaign_type: "text", use_gpt: true, gpt_prompt: "",
  message_template: "", include_products: false, product_count: 3, image_url: "",
  poll_question: "", poll_options: "", buttons: "", footer_text: "",
  campaign_scope: "pv", group_ids: "",
  description: "", contact_group_id: "", wa_collection_id: "", product_label_filter: "",
  emoji_level: "medium",
  append_seller_name: false, seller_name: "",
  append_seller_phone: false, seller_phone: "", seller_phone2: "",
  append_date: false,
};

function seedCampaignForm(d) {
  const join = (v) => (Array.isArray(v) ? v.join("\n") : (v || ""));
  return {
    name: d.name || "",
    campaign_type: d.campaign_type || "text",
    use_gpt: d.use_gpt ?? true,
    gpt_prompt: d.gpt_prompt || "",
    message_template: d.message_template || "",
    include_products: d.include_products || false,
    product_count: d.product_count || 3,
    image_url: d.image_url || "",
    poll_question: d.poll_question || "",
    poll_options: join(d.poll_options),
    buttons: join(d.buttons),
    footer_text: d.footer_text || "",
    campaign_scope: d.campaign_scope || "pv",
    group_ids: join(d.group_ids),
    description: d.description || "",
    contact_group_id: d.contact_group_id || "",
    wa_collection_id: d.wa_collection_id || "",
    product_label_filter: d.product_label_filter || "",
    emoji_level: d.emoji_level || "medium",
    append_seller_name: d.append_seller_name || false,
    seller_name: d.seller_name || "",
    append_seller_phone: d.append_seller_phone || false,
    seller_phone: d.seller_phone || "",
    seller_phone2: d.seller_phone2 || "",
    append_date: d.append_date || false,
  };
}

function AddCampaignModal({ onClose, onDone, editId = null, initial = null }) {
  const [f, setF] = React.useState(() => (initial ? seedCampaignForm(initial) : { ...CAMPAIGN_DEFAULTS }));
  const [saving, setSaving] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [contactGroups, setContactGroups] = React.useState([]);
  const [waCollections, setWaCollections] = React.useState([]);
  const [labels, setLabels] = React.useState([]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  // Load dropdown data once
  React.useEffect(() => {
    ContactGroupsApi.list().then(setContactGroups).catch(() => {});
    WaCollectionsApi.list().then(setWaCollections).catch(() => {});
    LabelsApi.list().then(setLabels).catch(() => {});
  }, []);

  // Prefill image_url + campaign type from a file chosen on the Files page (create mode only)
  React.useEffect(() => {
    if (editId) return;
    const pre = typeof localStorage !== "undefined" ? localStorage.getItem("afrakala_prefill_image_url") : "";
    if (pre) {
      setF((prev) => ({ ...prev, image_url: pre, campaign_type: "image" }));
      localStorage.removeItem("afrakala_prefill_image_url");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const uploadImage = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const accs = await Accounts.list();
      const active = accs.find((a) => a.status === "active") || accs[0];
      if (!active) return alert("حسابی برای آپلود موجود نیست");
      const fd = new FormData();
      fd.append("file", file);
      const r = await FilesApi.upload(active.id, fd);
      setF((prev) => ({ ...prev, image_url: r.url }));
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    if (!f.name) return alert("لطفاً نام گروه پیام را وارد کنید");
    setSaving(true);
    try {
      const body = {
        name: f.name,
        campaign_type: f.campaign_type,
        use_gpt: f.use_gpt,
        gpt_prompt: f.gpt_prompt || null,
        message_template: f.message_template || null,
        include_products: f.include_products,
        product_count: Number(f.product_count) || 3,
        image_url: f.image_url || null,
        poll_question: f.poll_question || null,
        poll_options: f.poll_options ? f.poll_options.split("\n").map((s) => s.trim()).filter(Boolean) : null,
        buttons: f.buttons ? f.buttons.split("\n").map((s) => s.trim()).filter(Boolean) : null,
        footer_text: f.footer_text || null,
        campaign_scope: f.campaign_scope,
        group_ids:
          f.campaign_scope === "group" && f.group_ids
            ? f.group_ids.split("\n").map((s) => s.trim()).filter(Boolean)
            : null,
        description: f.description || null,
        contact_group_id: f.contact_group_id || null,
        wa_collection_id: f.wa_collection_id || null,
        product_label_filter: f.include_products && f.product_label_filter ? f.product_label_filter : null,
        emoji_level: f.emoji_level,
        append_seller_name: f.append_seller_name,
        seller_name: f.append_seller_name ? (f.seller_name || null) : null,
        append_seller_phone: f.append_seller_phone,
        seller_phone: f.append_seller_phone ? (f.seller_phone || null) : null,
        seller_phone2: f.append_seller_phone ? (f.seller_phone2 || null) : null,
        append_date: f.append_date,
      };
      if (editId) {
        await Api.update(editId, body);
      } else {
        await Api.create(body);
      }
      await onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={editId ? "ویرایش کمپین" : "گروه پیام جدید"} onClose={onClose} wide>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">نام گروه پیام</label>
            <input className="input" value={f.name} onChange={set("name")} />
          </div>
          <div>
            <label className="label">نوع پیام</label>
            <select className="input" value={f.campaign_type} onChange={set("campaign_type")}>
              {Object.entries(TYPE_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label className="label">توضیحات کمپین (اختیاری)</label>
          <textarea className="input h-16" value={f.description} onChange={set("description")} />
        </div>

        <div>
          <label className="label">نوع ارسال</label>
          <select className="input" value={f.campaign_scope} onChange={set("campaign_scope")}>
            <option value="pv">ارسال به افراد</option>
            <option value="group">ارسال به گروه‌ها</option>
          </select>
        </div>

        {f.campaign_scope === "pv" && (
          <div>
            <label className="label">گروه مخاطبین (جایگزین افزودن دستی مخاطبین)</label>
            <select className="input" value={f.contact_group_id} onChange={set("contact_group_id")}>
              <option value="">— انتخاب نشده —</option>
              {contactGroups.map((g) => (
                <option key={g.id} value={g.id}>{g.name}{g.member_count != null ? ` (${g.member_count})` : ""}</option>
              ))}
            </select>
          </div>
        )}

        {f.campaign_scope === "group" && (
          <>
            <div>
              <label className="label">مجموعه گروه‌های واتساپ</label>
              <select className="input" value={f.wa_collection_id} onChange={set("wa_collection_id")}>
                <option value="">— انتخاب نشده —</option>
                {waCollections.map((w) => (
                  <option key={w.id} value={w.id}>{w.name}{w.group_count != null ? ` (${w.group_count})` : ""}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">شناسه گروه‌ها (هر خط یک گروه)</label>
              <textarea className="input h-20" value={f.group_ids} onChange={set("group_ids")} placeholder="120363xxxxxxxx@g.us" />
            </div>
          </>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.use_gpt} onChange={set("use_gpt")} />
          نوشتن پیام با هوش مصنوعی
        </label>
        <p className="text-xs text-slate-500 -mt-1">سیستم با هوش مصنوعی یک پیام منحصربه‌فرد برای هر مخاطب می‌نویسد</p>

        {f.use_gpt ? (
          <div>
            <label className="label">توضیح برای هوش مصنوعی</label>
            <textarea className="input h-20" value={f.gpt_prompt} onChange={set("gpt_prompt")} placeholder="مثال: یک پیام صمیمی و کوتاه برای مشتری عمده‌فروش لوازم خانگی بنویس که از خرید از افراکالا تشکر کند" />
          </div>
        ) : (
          <div>
            <label className="label">قالب پیام (می‌توانید از {"{{first_name}}"} استفاده کنید)</label>
            <textarea className="input h-20" value={f.message_template} onChange={set("message_template")} />
          </div>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.include_products} onChange={set("include_products")} />
          افزودن محصولات روز افراکالا
        </label>
        <p className="text-xs text-slate-500 -mt-1">قیمت لحظه‌ای محصولات افراکالا در پیام درج می‌شود</p>

        {f.include_products && (
          <>
            <div>
              <label className="label">تعداد محصول</label>
              <input
                type="number"
                className="input"
                min={1}
                max={10}
                value={f.product_count}
                onChange={set("product_count")}
              />
            </div>
            <div>
              <label className="label">فیلتر بر اساس برچسب (اختیاری)</label>
              <select className="input" value={f.product_label_filter} onChange={set("product_label_filter")}>
                <option value="">— همه محصولات —</option>
                {labels.map((l) => (
                  <option key={l.id} value={l.id}>{l.title}</option>
                ))}
              </select>
              {f.product_label_filter && (() => {
                const sel = labels.find((l) => String(l.id) === String(f.product_label_filter));
                return sel?.color ? (
                  <span className="inline-flex items-center gap-2 mt-1 text-xs text-slate-400">
                    <span className="inline-block w-3 h-3 rounded-full" style={{ backgroundColor: sel.color }} />
                    {sel.title}
                  </span>
                ) : null;
              })()}
            </div>
          </>
        )}

        {f.campaign_type === "image" && (
          <div>
            <label className="label">آدرس تصویر</label>
            <div className="flex gap-2">
              <input className="input flex-1" value={f.image_url} onChange={set("image_url")} />
              <label className="btn-secondary cursor-pointer whitespace-nowrap">
                {uploading ? "در حال آپلود..." : "آپلود فایل"}
                <input type="file" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0])} />
              </label>
            </div>
          </div>
        )}
        {f.campaign_type === "poll" && (
          <>
            <div>
              <label className="label">سؤال نظرسنجی</label>
              <input className="input" value={f.poll_question} onChange={set("poll_question")} />
            </div>
            <div>
              <label className="label">گزینه‌ها (هر خط یک گزینه)</label>
              <textarea className="input h-20" value={f.poll_options} onChange={set("poll_options")} />
            </div>
          </>
        )}
        {f.campaign_type === "interactive_buttons" && (
          <>
            <div>
              <label className="label">دکمه‌ها (هر خط یک دکمه، حداکثر ۳)</label>
              <textarea className="input h-16" value={f.buttons} onChange={set("buttons")} />
            </div>
            <div>
              <label className="label">متن پاورقی</label>
              <input className="input" value={f.footer_text} onChange={set("footer_text")} />
            </div>
          </>
        )}

        <div>
          <label className="label">سطح ایموجی</label>
          <select className="input" value={f.emoji_level} onChange={set("emoji_level")}>
            {EMOJI_LEVELS.map((e) => <option key={e.code} value={e.code}>{e.label}</option>)}
          </select>
        </div>

        <div className="rounded-lg border border-slate-700 p-3 space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.append_seller_name} onChange={set("append_seller_name")} />
            نام فروشنده اضافه شود
          </label>
          {f.append_seller_name && (
            <div>
              <label className="label">نام فروشنده</label>
              <input className="input" value={f.seller_name} onChange={set("seller_name")} />
            </div>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.append_seller_phone} onChange={set("append_seller_phone")} />
            شماره فروشنده اضافه شود
          </label>
          {f.append_seller_phone && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">موبایل</label>
                <input className="input" value={f.seller_phone} onChange={set("seller_phone")} />
              </div>
              <div>
                <label className="label">تلفن ثابت</label>
                <input className="input" value={f.seller_phone2} onChange={set("seller_phone2")} />
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.append_date} onChange={set("append_date")} />
            تاریخ امروز (شمسی) آخر پیام اضافه شود
          </label>
        </div>

        <button className="btn-primary w-full" disabled={saving} onClick={submit}>
          {saving ? (editId ? "در حال ذخیره..." : "در حال ساخت...") : (editId ? "ذخیره تغییرات" : "ساخت گروه پیام")}
        </button>
        {!editId && <p className="text-xs text-slate-500">پس از ساخت، مخاطبین را از صفحه مخاطبین اضافه کنید و سپس گروه پیام را شروع کنید.</p>}
      </div>
    </Modal>
  );
}

function TestModal({ campaign, onClose }) {
  const [phone, setPhone] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [sending, setSending] = React.useState(false);

  const send = async () => {
    if (!phone) return alert("لطفاً شماره را وارد کنید");
    setSending(true);
    try {
      const r = await Api.test(campaign.id, phone, message || null);
      alert(r.sent ? `ارسال شد (از ${r.via})` : "ارسال ناموفق");
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal title={`تست گروه پیام: ${campaign.name}`} onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="label">شماره تست</label>
          <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="09123456789" />
        </div>
        <div>
          <label className="label">پیام دلخواه (اختیاری)</label>
          <textarea className="input h-20" value={message} onChange={(e) => setMessage(e.target.value)} />
        </div>
        <p className="text-xs text-slate-500">پیام آزمایشی با همین تنظیمات GPT و محصولات ارسال می‌شود</p>
        <button className="btn-primary w-full" disabled={sending} onClick={send}>
          {sending ? "در حال ارسال..." : "ارسال تست"}
        </button>
      </div>
    </Modal>
  );
}
