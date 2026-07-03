import React from "react";
import { Campaigns as Api, FilesApi, Accounts } from "../api.js";
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

  const act = async (fn) => {
    try {
      await fn();
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
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

function AddCampaignModal({ onClose, onDone }) {
  const [f, setF] = React.useState({
    name: "", campaign_type: "text", use_gpt: true, gpt_prompt: "",
    message_template: "", include_products: false, product_count: 3, image_url: "",
    poll_question: "", poll_options: "", buttons: "", footer_text: "",
    campaign_scope: "pv", group_ids: "",
  });
  const [saving, setSaving] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  // Prefill image_url + campaign type from a file chosen on the Files page
  React.useEffect(() => {
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
      };
      await Api.create(body);
      await onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="گروه پیام جدید" onClose={onClose} wide>
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
          <label className="label">نوع ارسال</label>
          <select className="input" value={f.campaign_scope} onChange={set("campaign_scope")}>
            <option value="pv">ارسال به افراد</option>
            <option value="group">ارسال به گروه‌ها</option>
          </select>
        </div>

        {f.campaign_scope === "group" && (
          <div>
            <label className="label">شناسه گروه‌ها (هر خط یک گروه)</label>
            <textarea className="input h-20" value={f.group_ids} onChange={set("group_ids")} placeholder="120363xxxxxxxx@g.us" />
          </div>
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

        <button className="btn-primary w-full" disabled={saving} onClick={submit}>
          {saving ? "در حال ساخت..." : "ساخت گروه پیام"}
        </button>
        <p className="text-xs text-slate-500">پس از ساخت، مخاطبین را از صفحه مخاطبین اضافه کنید و سپس گروه پیام را شروع کنید.</p>
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
