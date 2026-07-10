import React from "react";
import { JoinLinksApi as Api, Accounts as AccApi } from "../api.js";
import { Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

const TYPE_LABELS = {
  group: "گروه",
  community: "انجمن",
  broadcast: "لیست انتشار",
};

const TYPE_BADGE = {
  group: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  community: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  broadcast: "bg-purple-500/20 text-purple-300 border-purple-500/40",
};

const STATUS_LABELS = {
  joined: "عضو شد",
  pending: "در انتظار",
  unsupported: "پشتیبانی نمی‌شود",
  error: "خطا",
};

const STATUS_BADGE = {
  joined: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  pending: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  unsupported: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  error: "bg-red-500/20 text-red-300 border-red-500/40",
};

const looksLikeUrl = (s) => /^https?:\/\//i.test(s) || /^[\w.-]+\.[a-z]{2,}/i.test(s);

export default function JoinLinks() {
  const [links, setLinks] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [accounts, setAccounts] = React.useState([]);
  const [accountId, setAccountId] = React.useState("");

  const [status, setStatus] = React.useState([]);

  // single add form
  const [name, setName] = React.useState("");
  const [link, setLink] = React.useState("");
  const [type, setType] = React.useState("group");
  const [adding, setAdding] = React.useState(false);

  // bulk paste
  const [bulk, setBulk] = React.useState("");
  const [bulkAdding, setBulkAdding] = React.useState(false);

  const [joining, setJoining] = React.useState(false);

  const loadLinks = React.useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await Api.list();
      setLinks(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setLinks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStatus = React.useCallback(async () => {
    try {
      const data = await Api.status();
      setStatus(Array.isArray(data) ? data : []);
    } catch {
      setStatus([]);
    }
  }, []);

  React.useEffect(() => {
    loadLinks();
    loadStatus();
    AccApi.list()
      .then((list) => {
        const arr = Array.isArray(list) ? list : [];
        setAccounts(arr);
        const active = arr.find((a) => a.status === "authorized" || a.status === "active");
        const def = active || arr[0];
        if (def) setAccountId(String(def.id));
      })
      .catch(() => {});
  }, [loadLinks, loadStatus]);

  const addSingle = async () => {
    if (!link.trim()) return toast.error("لینک دعوت لازم است");
    setAdding(true);
    try {
      await Api.add(name.trim(), link.trim(), type);
      setName("");
      setLink("");
      setType("group");
      await loadLinks();
      toast.success("لینک افزوده شد");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setAdding(false);
    }
  };

  const addBulk = async () => {
    const arr = bulk
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l && looksLikeUrl(l))
      .map((l) => ({ name: "", invite_link: l, link_type: "group" }));
    if (arr.length === 0) return toast.error("هیچ لینک معتبری یافت نشد");
    setBulkAdding(true);
    try {
      const r = await Api.bulk(arr);
      setBulk("");
      await loadLinks();
      toast.success(`${fa(r?.added)} لینک افزوده شد`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBulkAdding(false);
    }
  };

  const remove = async (id) => {
    if (!(await confirmDialog("حذف این لینک؟"))) return;
    try {
      await Api.delete(id);
      await loadLinks();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const joinAll = async () => {
    if (!accountId) return toast.error("ابتدا یک حساب انتخاب کنید");
    setJoining(true);
    try {
      const r = await Api.joinAll(accountId);
      toast.info(`تلاش برای عضویت در ${fa(r?.links_to_join)} لینک شروع شد (وضعیت در جدول)`);
      setTimeout(() => {
        loadStatus();
      }, 2000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setJoining(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">لینک‌های گروه و کانال</h2>

      <div className="card bg-amber-500/10 border-amber-500/30 text-amber-200 text-sm">
        ⚠️ واتساپ/Green API معمولاً پیوستن خودکار به گروه از طریق لینک را محدود می‌کند. لینک‌ها اینجا
        ثبت و مدیریت می‌شوند؛ در صورت پشتیبانی نشدن، عضویت باید از روی گوشی انجام شود. وضعیت هر تلاش در
        جدول پایین نمایش داده می‌شود.
      </div>

      {/* Add single link */}
      <div className="card space-y-3">
        <h3 className="font-bold text-sm">افزودن لینک</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label">نام (اختیاری)</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="label">نوع</label>
            <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="group">گروه</option>
              <option value="community">انجمن</option>
              <option value="broadcast">لیست انتشار</option>
            </select>
          </div>
        </div>
        <div>
          <label className="label">لینک دعوت</label>
          <input
            className="input"
            dir="ltr"
            placeholder="https://chat.whatsapp.com/..."
            value={link}
            onChange={(e) => setLink(e.target.value)}
          />
        </div>
        <button className="btn-primary" disabled={adding} onClick={addSingle}>
          {adding ? "..." : "افزودن"}
        </button>
      </div>

      {/* Bulk paste */}
      <div className="card space-y-3">
        <h3 className="font-bold text-sm">افزودن گروهی</h3>
        <div>
          <label className="label">چند لینک (هر خط یک لینک)</label>
          <textarea
            className="input h-28"
            dir="ltr"
            placeholder={"https://chat.whatsapp.com/...\nhttps://chat.whatsapp.com/..."}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
          />
        </div>
        <button className="btn-secondary" disabled={bulkAdding} onClick={addBulk}>
          {bulkAdding ? "..." : "افزودن گروهی"}
        </button>
      </div>

      {/* Links list */}
      <div className="space-y-3">
        {loading && <Spinner />}
        {error && <div className="card text-red-400">{error}</div>}
        {links && links.length === 0 && <Empty label="لینکی ثبت نشده است." />}
        {links && links.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {links.map((l) => (
              <div key={l.id} className="card space-y-2">
                <div className="flex items-center gap-2">
                  <span className="font-bold truncate">{l.name || l.invite_link}</span>
                  <span className={`badge mr-auto ${TYPE_BADGE[l.link_type] || TYPE_BADGE.group}`}>
                    {TYPE_LABELS[l.link_type] || l.link_type || "گروه"}
                  </span>
                </div>
                <p className="text-xs text-slate-400 font-mono break-all" dir="ltr">
                  {l.invite_link}
                </p>
                <button className="btn-danger text-xs" onClick={() => remove(l.id)}>
                  حذف
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Join controls */}
      <div className="card space-y-3">
        <h3 className="font-bold text-sm">عضویت با یک حساب</h3>
        <div className="flex flex-wrap gap-2">
          <select
            className="input sm:max-w-xs"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
          >
            {accounts.length === 0 && <option value="">حسابی موجود نیست</option>}
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <button className="btn-primary whitespace-nowrap" disabled={joining} onClick={joinAll}>
            {joining ? "در حال شروع..." : "🔗 عضویت در همه با این حساب"}
          </button>
        </div>
      </div>

      {/* Status table */}
      <div className="card space-y-3">
        <h3 className="font-bold text-sm">وضعیت تلاش‌ها</h3>
        {(!status || status.length === 0) && (
          <p className="text-slate-500 text-sm">هنوز تلاشی برای عضویت ثبت نشده.</p>
        )}
        {status && status.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-right border-b border-slate-700">
                  <th className="py-2 px-2 font-medium">حساب</th>
                  <th className="py-2 px-2 font-medium">لینک</th>
                  <th className="py-2 px-2 font-medium">وضعیت</th>
                  <th className="py-2 px-2 font-medium">خطا</th>
                </tr>
              </thead>
              <tbody>
                {status.map((s, i) => (
                  <tr key={`${s.account_id}-${s.link_id}-${i}`} className="border-b border-slate-800">
                    <td className="py-2 px-2 truncate max-w-[10rem]">{s.account || s.account_id}</td>
                    <td className="py-2 px-2 font-mono text-xs truncate max-w-[14rem]" dir="ltr">
                      {s.link}
                    </td>
                    <td className="py-2 px-2">
                      <span className={`badge ${STATUS_BADGE[s.status] || STATUS_BADGE.pending}`}>
                        {STATUS_LABELS[s.status] || s.status}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-red-300 text-xs truncate max-w-[14rem]">
                      {s.error || ""}
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
