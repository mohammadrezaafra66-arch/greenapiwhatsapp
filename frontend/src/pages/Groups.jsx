import React from "react";
import { Groups as Api, Accounts as AccApi } from "../api.js";
import { Spinner, Empty, Modal } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const CHAT_TYPE_LABELS = {
  group: { label: "گروه معمولی", icon: "👥", cls: "text-emerald-400" },
  broadcast: { label: "لیست انتشار", icon: "📢", cls: "text-sky-400" },
};

const MEMBER_FILTERS = [
  { label: "همه", min: 0 },
  { label: "+۱۰ نفر", min: 10 },
  { label: "+۵۰ نفر", min: 50 },
  { label: "+۱۰۰ نفر", min: 100 },
  { label: "+۵۰۰ نفر", min: 500 },
];

// NOTE: WhatsApp Broadcast lists are not returned by Green API's getChats, so
// they can never be synced — no "broadcast" tab is offered.
const TYPE_TABS = [
  { key: "all", label: "همه" },
  { key: "group", label: "👥 گروه" },
];

const ADMIN_TABS = [
  { label: "همه", val: null },
  { label: "👑 ادمین", val: true },
  { label: "عضو عادی", val: false },
];

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

export default function Groups() {
  const [groups, setGroups] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [search, setSearch] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState("all");
  const [isAdminFilter, setIsAdminFilter] = React.useState(null);
  const [minMembers, setMinMembers] = React.useState(0);
  const [accounts, setAccounts] = React.useState([]);
  const [selectedAccount, setSelectedAccount] = React.useState("");
  const [syncing, setSyncing] = React.useState(false);
  const [showAdd, setShowAdd] = React.useState(false);
  const [send, setSend] = React.useState(null);
  const [busy, setBusy] = React.useState(null);
  const [addMembers, setAddMembers] = React.useState(null);
  const [extracting, setExtracting] = React.useState(null); // group id being extracted
  const [extracted, setExtracted] = React.useState(null); // { group, phones, count } | null
  const [manage, setManage] = React.useState(null); // group being managed (F22)

  const extractMembers = async (g) => {
    setExtracting(g.id);
    try {
      const r = await Api.extractMembers(g.id);
      setExtracted({ group: g, phones: r.phones, count: r.count });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setExtracting(null);
    }
  };

  // Bulk extract members from ALL of this account's groups → contacts (background)
  const [extractingAll, setExtractingAll] = React.useState(false);
  const [extractProgress, setExtractProgress] = React.useState(null);
  const pollRef = React.useRef(null);

  React.useEffect(() => () => clearInterval(pollRef.current), []);

  const extractAllGroups = async () => {
    if (!selectedAccount) return toast.error("حساب فعالی انتخاب نشده است");
    if (!(await confirmDialog("استخراج اعضای همه گروه‌های این حساب و افزودن به مخاطبین؟ این کار در پس‌زمینه اجرا می‌شود."))) return;
    setExtractingAll(true);
    setExtractProgress(null);
    try {
      await Api.extractAll(selectedAccount, 0);
      clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const prog = await Api.extractProgress(selectedAccount);
          setExtractProgress(prog);
          if (prog.status === "completed" || prog.status === "idle") {
            clearInterval(pollRef.current);
            setExtractingAll(false);
            if (prog.status === "completed") {
              toast.success(`استخراج تکمیل شد!\nافزوده‌شده: ${prog.added}\nتکراری/نامعتبر: ${prog.skipped}`);
            }
          }
        } catch {
          /* keep polling */
        }
      }, 3000);
    } catch (e) {
      setExtractingAll(false);
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const loadGroups = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      // V15 Item 2 — filter groups by the selected account. "all"/empty = every account.
      if (selectedAccount && selectedAccount !== "all") params.account_id = selectedAccount;
      if (typeFilter !== "all") params.chat_type = typeFilter;
      if (isAdminFilter !== null) params.is_admin = isAdminFilter;
      if (minMembers > 0) params.min_members = minMembers;
      setGroups(await Api.list(params));
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedAccount, typeFilter, isAdminFilter, minMembers]);

  React.useEffect(() => {
    AccApi.list()
      .then((a) => {
        setAccounts(a || []);
        const act = (a || []).find((x) => x.status === "active");
        if (act) setSelectedAccount(act.id);
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => { loadGroups(); }, [loadGroups]);

  const activeAccounts = accounts.filter((a) => a.status === "active");
  const filtered = groups.filter((g) => g.name?.includes(search) || g.group_chat_id?.includes(search));

  const syncGroups = async () => {
    if (!selectedAccount) return toast.error("حساب فعالی انتخاب نشده است");
    setSyncing(true);
    try {
      const r = await Api.sync(selectedAccount);
      toast.success(`${r.synced_new} گروه جدید + ${r.updated} به‌روزرسانی شد`);
      await loadGroups();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSyncing(false);
    }
  };

  const refreshMembers = async (gid) => {
    setBusy(gid);
    try {
      await Api.refreshMembers(gid);
      await loadGroups();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(null);
    }
  };

  const copyId = (id) => {
    navigator.clipboard?.writeText(id);
    toast.success("شناسه کپی شد");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-2xl font-bold">گروه‌های واتساپ</h2>
        <div className="flex gap-2 flex-wrap">
          <select className="input w-auto" value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value)}>
            {/* V15 Item 19 — explicit "all accounts" option */}
            <option value="all">همه اکانت‌ها</option>
            {activeAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}{a.phone ? ` (${a.phone})` : ""}</option>)}
          </select>
          <button className="btn-secondary" disabled={syncing} onClick={syncGroups}>
            {syncing ? "در حال همگام‌سازی..." : "🔄 همگام‌سازی با واتساپ"}
          </button>
          <button className="btn-secondary" disabled={extractingAll} onClick={extractAllGroups}>
            {extractingAll
              ? `⏳ استخراج... (${fa(extractProgress?.processed ?? 0)}/${fa(extractProgress?.total ?? 0)})`
              : "📥 استخراج اعضای همه گروه‌ها"}
          </button>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>+ ساخت گروه</button>
        </div>
      </div>

      {extractProgress && extractProgress.status === "running" && (
        <div className="card bg-amber-500/10 border-amber-500/30 space-y-1">
          <div className="flex justify-between text-sm text-amber-200">
            <span className="truncate">در حال استخراج: {extractProgress.current_group || "…"}</span>
            <span>{fa(extractProgress.processed)}/{fa(extractProgress.total)} گروه</span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-2">
            <div
              className="bg-amber-500 h-2 rounded-full transition-all"
              style={{ width: `${extractProgress.total ? (extractProgress.processed / extractProgress.total) * 100 : 0}%` }}
            />
          </div>
          <p className="text-xs text-slate-400">افزوده‌شده: {fa(extractProgress.added)} · تکراری/نامعتبر: {fa(extractProgress.skipped)}</p>
        </div>
      )}

      <div className="card text-sm text-sky-300 bg-sky-500/10 border-sky-500/30">
        💡 برای نمایش گروه‌ها ابتدا «همگام‌سازی با واتساپ» را بزنید. فقط گروه‌های معمولی (که عضوشان هستید) دریافت می‌شوند. لیست‌های انتشار (Broadcast) و کانال‌های واتساپ توسط Green API ارائه نمی‌شوند و اینجا نمایش داده نمی‌شوند.
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          className="input flex-1 min-w-48"
          placeholder="جستجو بر اساس نام گروه یا شناسه..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
          {TYPE_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTypeFilter(t.key)}
              className={`px-3 py-1 rounded text-sm ${typeFilter === t.key ? "bg-brand text-white" : "text-slate-400 hover:text-slate-200"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
          {ADMIN_TABS.map((t) => (
            <button
              key={String(t.val)}
              onClick={() => setIsAdminFilter(t.val)}
              className={`px-3 py-1 rounded text-sm ${isAdminFilter === t.val ? "bg-brand text-white" : "text-slate-400 hover:text-slate-200"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <select className="input w-auto" value={minMembers} onChange={(e) => setMinMembers(Number(e.target.value))}>
          {MEMBER_FILTERS.map((f) => <option key={f.min} value={f.min}>{f.label}</option>)}
        </select>
      </div>

      <div className="text-sm text-slate-400">
        {fa(filtered.length)} گروه نمایش داده می‌شود
        {groups.length !== filtered.length && ` (از ${fa(groups.length)} کل)`}
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {!loading && filtered.length === 0 && (
        <Empty label={groups.length === 0 ? "گروهی پیدا نشد — ابتدا همگام‌سازی کنید." : "گروهی با این فیلترها پیدا نشد."} />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((g) => {
          const t = CHAT_TYPE_LABELS[g.chat_type] || CHAT_TYPE_LABELS.group;
          return (
            <div key={g.id} className="card space-y-2">
              <div className="flex justify-between items-start gap-2">
                <h3 className="font-bold text-sm leading-tight">
                  {/* V15 Item 20 — always show a name; fall back to the id + «(بدون نام)» */}
                  {g.name && g.name.trim()
                    ? g.name
                    : <span className="text-slate-400 font-mono">{g.group_chat_id || "—"} <span className="text-xs">(بدون نام)</span></span>}
                  {g.is_admin && <span className="text-xs text-amber-400 font-bold mr-2">👑 ادمین</span>}
                </h3>
                <span className={`text-xs whitespace-nowrap ${t.cls}`}>{t.icon} {t.label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-emerald-400">{g.member_count > 0 ? fa(g.member_count) : "—"}</span>
                <span className="text-slate-400 text-sm">عضو</span>
                <button
                  className="text-xs text-slate-500 hover:text-slate-300 mr-auto disabled:opacity-40"
                  disabled={busy === g.id}
                  title="به‌روزرسانی تعداد اعضا"
                  onClick={() => refreshMembers(g.id)}
                >
                  {busy === g.id ? "…" : "🔄"}
                </button>
              </div>
              {g.description && <p className="text-slate-400 text-xs line-clamp-2">{g.description}</p>}
              <p className="text-slate-500 text-xs font-mono truncate">{g.group_chat_id || "بدون شناسه"}</p>
              <div className="flex gap-2">
                <button className="btn-secondary flex-1 text-xs" onClick={() => setSend(g)}>ارسال پیام</button>
                <button className="btn-secondary text-xs px-2" title="کپی شناسه" onClick={() => copyId(g.group_chat_id)}>📋</button>
              </div>
              <button
                className="btn-secondary text-xs w-full disabled:opacity-50"
                disabled={extracting === g.id}
                onClick={() => extractMembers(g)}
              >
                {extracting === g.id ? "در حال استخراج..." : "👥 استخراج اعضا"}
              </button>
              {g.is_admin && (
                <button className="btn-secondary text-xs w-full" onClick={() => setAddMembers(g)}>
                  ➕ افزودن اعضا از اکسل
                </button>
              )}
              {g.is_admin && g.group_chat_id && (
                <button className="btn-secondary text-xs w-full" onClick={() => setManage(g)}>
                  ⚙️ مدیریت گروه
                </button>
              )}
            </div>
          );
        })}
      </div>

      {showAdd && <AddGroupModal onClose={() => setShowAdd(false)} onDone={loadGroups} />}
      {send && <SendModal group={send} onClose={() => setSend(null)} />}
      {addMembers && <AddMembersModal group={addMembers} onClose={() => setAddMembers(null)} />}
      {extracted && <ExtractedMembersModal data={extracted} onClose={() => setExtracted(null)} />}
      {manage && <GroupManagerModal group={manage} onClose={() => setManage(null)} onChanged={loadGroups} />}
    </div>
  );
}

// FEATURE 22 — full group manager (⚠️ highest ban risk). Warning banner + participants
// table + settings toggles + ban-guarded add pipeline with live per-number progress.
function GroupManagerModal({ group, onClose, onChanged }) {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [tab, setTab] = React.useState("members"); // members | add | settings
  const [addText, setAddText] = React.useState("");
  const [prog, setProg] = React.useState(null);
  const acct = group.account_id;
  const gid = group.id;
  const gchat = group.group_chat_id;

  const load = React.useCallback(() => {
    setLoading(true);
    Api.data(gid).then(setData).catch((e) => toast.error(e?.response?.data?.detail || e.message)).finally(() => setLoading(false));
  }, [gid]);
  React.useEffect(() => { load(); }, [load]);

  const participants = (data?.participants) || [];
  const inviteLink = data?.groupInviteLink;

  async function startAdd() {
    const phones = addText.split(/[\n,،]+/).map((s) => s.trim()).filter(Boolean);
    if (!phones.length) return toast.error("شماره‌ای وارد نشده");
    try {
      await Api.safeAdd(gid, phones);
      setProg({ total: phones.length, results: [], finished: false });
      const t = setInterval(async () => {
        try {
          const p = await Api.safeAddProgress(gid);
          setProg(p);
          if (p.finished) { clearInterval(t); onChanged && onChanged(); }
        } catch { /* ignore */ }
      }, 1500);
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  const STATUS_FA = { added: "✅ افزوده شد", no_whatsapp: "⛔ واتساپ ندارد", queued: "⏳ در نوبت", failed: "❌ ناموفق — دعوت بفرستید" };

  return (
    <Modal title={`مدیریت گروه: ${group.name}`} onClose={onClose} wide>
      <div className="space-y-3">
        <div className="card bg-red-500/10 border-red-500/40 text-red-200 text-xs">
          ⚠️ افزودن عضو به گروه پرخطرترین کار در واتساپ است. افزودن شماره‌ای که واتساپ ندارد می‌تواند باعث مسدود شدن خط شما شود.
          سامانه قبل از افزودن، وجود واتساپ را چک می‌کند و سرعت را محدود می‌کند (۵ در دقیقه). بهتر است ابتدا در پیام خصوصی از فرد اجازه بگیرید.
        </div>

        <div className="flex gap-2 items-center flex-wrap">
          <button className={tab === "members" ? "btn-primary text-xs" : "btn-secondary text-xs"} onClick={() => setTab("members")}>اعضا</button>
          <button className={tab === "add" ? "btn-primary text-xs" : "btn-secondary text-xs"} onClick={() => setTab("add")}>➕ افزودن عضو</button>
          <button className={tab === "settings" ? "btn-primary text-xs" : "btn-secondary text-xs"} onClick={() => setTab("settings")}>تنظیمات</button>
          {inviteLink && <button className="btn-secondary text-xs mr-auto" onClick={() => { navigator.clipboard?.writeText(inviteLink); toast.success("لینک دعوت کپی شد"); }}>📋 لینک دعوت</button>}
        </div>

        {loading ? <Spinner /> : tab === "members" ? (
          <div className="max-h-80 overflow-y-auto">
            <p className="text-xs text-slate-400 mb-2">اعضا: {participants.length} {data?.size ? `از ${data.size}` : ""}</p>
            <table className="w-full text-sm">
              <tbody>
                {participants.map((p, i) => {
                  const phone = String(p.id || "").split("@")[0];
                  const isAdmin = p.isAdmin || p.isSuperAdmin;
                  return (
                    <tr key={i} className="border-t border-slate-800">
                      <td className="p-1 font-mono text-xs">{phone}</td>
                      <td className="p-1">{isAdmin && <span className="text-amber-400 text-xs">👑 ادمین</span>}</td>
                      <td className="p-1 text-left">
                        <div className="flex gap-1 justify-end flex-wrap">
                          {!isAdmin && <button className="btn-secondary text-xs" onClick={async () => { try { await Api.promote(gchat, phone, acct); toast.success("ادمین شد"); load(); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } }}>ارتقا</button>}
                          {isAdmin && !p.isSuperAdmin && <button className="btn-secondary text-xs" onClick={async () => { try { await Api.demote(gchat, phone, acct); toast.success("حذف ادمین شد"); load(); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } }}>حذف ادمین</button>}
                          <button className="btn-danger text-xs" onClick={async () => { if (await confirmDialog(`حذف ${phone} از گروه؟`)) { try { await Api.removeMember(gchat, phone); toast.success("حذف شد"); load(); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } } }}>حذف</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : tab === "add" ? (
          <div className="space-y-2">
            <textarea className="input h-24" placeholder="شماره‌ها را با کاما یا خط جدید وارد کنید" value={addText} onChange={(e) => setAddText(e.target.value)} />
            <button className="btn-primary w-full" onClick={startAdd}>➕ افزودن با بررسی ایمنی</button>
            {prog && (
              <div className="card space-y-1 max-h-56 overflow-y-auto">
                <p className="text-xs text-slate-400">{prog.finished ? "✅ پایان" : "در حال افزودن…"} ({(prog.results || []).length} / {prog.total})</p>
                {prog.error && <p className="text-red-300 text-xs">{prog.error}</p>}
                {(prog.results || []).map((r, i) => (
                  <div key={i} className="flex justify-between text-xs">
                    <span className="font-mono">{r.phone}</span>
                    <span>{STATUS_FA[r.status] || r.status}</span>
                  </div>
                ))}
                {prog.finished && (prog.results || []).some((r) => r.status === "failed") && inviteLink && (
                  <button className="btn-secondary text-xs w-full mt-1" onClick={() => { navigator.clipboard?.writeText(inviteLink); toast.success("لینک دعوت کپی شد — برای ناموفق‌ها بفرستید"); }}>📋 کپی لینک دعوت برای ناموفق‌ها</button>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <button className="btn-secondary w-full text-sm" onClick={async () => { try { await Api.settings(gid, { allow_send: false }); toast.success("فقط ادمین‌ها می‌توانند پیام بفرستند"); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } }}>فقط ادمین‌ها پیام بفرستند</button>
            <button className="btn-secondary w-full text-sm" onClick={async () => { try { await Api.settings(gid, { allow_send: true }); toast.success("همه می‌توانند پیام بفرستند"); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } }}>همه بتوانند پیام بفرستند</button>
            <button className="btn-secondary w-full text-sm" onClick={async () => { try { await Api.settings(gid, { allow_edit: false }); toast.success("فقط ادمین‌ها تنظیمات را تغییر دهند"); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } }}>فقط ادمین‌ها تنظیمات را تغییر دهند</button>
            <label className="btn-secondary cursor-pointer w-full text-sm block text-center">
              🖼 تغییر عکس گروه
              <input type="file" accept="image/*" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; try { await Api.setPicture(gid, f); toast.success("عکس گروه تنظیم شد"); } catch (err) { toast.error(err?.response?.data?.detail || err.message); } }} />
            </label>
            <button className="btn-danger w-full text-sm" onClick={async () => { if (await confirmDialog(`از گروه «${group.name}» خارج می‌شوید؟`)) { try { await Api.leave(gchat, acct); toast.success("از گروه خارج شدید"); onClose(); onChanged && onChanged(); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } } }}>🚪 خروج از گروه</button>
          </div>
        )}
      </div>
    </Modal>
  );
}

function ExtractedMembersModal({ data, onClose }) {
  const { group, phones, count } = data;
  const [importing, setImporting] = React.useState(false);
  const [result, setResult] = React.useState(null);

  const importToContacts = async () => {
    setImporting(true);
    try {
      const r = await Api.importMembersToContacts(group.id, phones);
      setResult(r);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <Modal title={`اعضای گروه: ${group.name}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-slate-300">{fa(count)} شماره استخراج شد</p>
        <div className="max-h-64 overflow-y-auto bg-slate-900 rounded-lg p-2 text-xs font-mono text-slate-400 space-y-0.5" dir="ltr">
          {phones.length === 0 ? (
            <p className="text-slate-500">شماره‌ای یافت نشد.</p>
          ) : (
            phones.map((p) => <div key={p}>{p}</div>)
          )}
        </div>
        {result ? (
          <div className="card bg-emerald-500/10 border-emerald-500/30 text-sm text-emerald-300">
            ✅ {fa(result.added)} مخاطب جدید افزوده شد · {fa(result.skipped)} تکراری · {fa(result.invalid)} نامعتبر
          </div>
        ) : (
          <button className="btn-primary w-full" disabled={importing || phones.length === 0} onClick={importToContacts}>
            {importing ? "در حال افزودن..." : "افزودن به مخاطبین"}
          </button>
        )}
      </div>
    </Modal>
  );
}

function AddMembersModal({ group, onClose }) {
  const [membersFile, setMembersFile] = React.useState(null);
  const [running, setRunning] = React.useState(false);
  const [result, setResult] = React.useState(null);

  const start = async () => {
    if (!membersFile) return toast.error("ابتدا فایل اکسل را انتخاب کنید");
    if (!group.account_id) return toast.error("حساب گروه مشخص نیست");
    setRunning(true);
    try {
      const r = await Api.importExcelToGroup(group.group_chat_id, group.account_id, membersFile);
      setResult(r);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Modal title={`افزودن اعضا به ${group.name}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-slate-400">
          فایل اکسل با ستون phone آپلود کنید. اعضا به‌صورت خودکار اضافه می‌شوند. فقط در گروه‌هایی که ادمین هستید کار می‌کند.
        </p>
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={(e) => setMembersFile(e.target.files[0])}
          className="input"
        />
        <button className="btn-primary w-full" disabled={running} onClick={start}>
          {running ? "در حال افزودن..." : "شروع افزودن"}
        </button>
        {result && (
          <div className="space-y-2">
            <p className="text-sm">
              ✅ {fa(result.added)} نفر اضافه شد | ❌ {fa(result.failed)} خطا
            </p>
            {Array.isArray(result.errors) && result.errors.length > 0 && (
              <div className="text-xs text-red-400 space-y-1">
                {result.errors.slice(0, 5).map((err, i) => (
                  <p key={i}>{typeof err === "string" ? err : JSON.stringify(err)}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

function AddGroupModal({ onClose, onDone }) {
  const [accounts, setAccounts] = React.useState([]);
  const [f, setF] = React.useState({ account_id: "", name: "", description: "", phones: "" });
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => { AccApi.list().then((a) => { setAccounts(a); if (a[0]) setF((p) => ({ ...p, account_id: a[0].id })); }); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.account_id || !f.name) return toast.error("حساب و نام لازم است");
    setSaving(true);
    try {
      await Api.create({
        account_id: f.account_id,
        name: f.name,
        description: f.description || null,
        phones: f.phones ? f.phones.split("\n").map((s) => s.trim()).filter(Boolean) : [],
      });
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="ساخت گروه جدید" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="label">حساب سازنده</label>
          <select className="input" value={f.account_id} onChange={set("account_id")}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div><label className="label">نام گروه</label><input className="input" value={f.name} onChange={set("name")} /></div>
        <div><label className="label">توضیحات</label><input className="input" value={f.description} onChange={set("description")} /></div>
        <div><label className="label">شماره اعضا (هر خط یک شماره)</label><textarea className="input h-24" value={f.phones} onChange={set("phones")} /></div>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "..." : "ساخت گروه"}</button>
      </div>
    </Modal>
  );
}

function SendModal({ group, onClose }) {
  const [text, setText] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const send = async () => {
    if (!text) return;
    setSending(true);
    try {
      const r = await Api.send(group.id, text);
      toast.info(r.sent ? "ارسال شد" : "ارسال ناموفق");
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };
  return (
    <Modal title={`ارسال به گروه: ${group.name}`} onClose={onClose}>
      <div className="space-y-3">
        <textarea className="input h-28" value={text} onChange={(e) => setText(e.target.value)} placeholder="متن پیام..." />
        <button className="btn-primary w-full" disabled={sending} onClick={send}>{sending ? "..." : "ارسال"}</button>
      </div>
    </Modal>
  );
}
