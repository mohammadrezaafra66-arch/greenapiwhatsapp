import React from "react";
import { Accounts, GroupMonitorApi as Api } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const MODE_FA = { off: "خاموش", predefined: "از پیش‌تعریف‌شده", ai: "هوش مصنوعی" };
const TABS = [
  ["groups", "پایش گروه‌ها"],
  ["keywords", "کلمات کلیدی"],
  ["replies", "پاسخ‌های آماده"],
  ["messages", "پیام‌های گروه"],
  ["alerts", "هشدارهای مدیر"],
];

export default function GroupMonitoring() {
  const [tab, setTab] = React.useState("groups");
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">پایش گروه‌ها 🎧</h2>
      <div className="card text-sm text-slate-300 bg-amber-500/10 border-amber-500/30">
        ⚠️ حساب «شنونده» فقط برای پایش گروه‌هاست و باید یک شماره جدا و سالم باشد. این حساب هرگز
        نباید در کمپین‌ها یا گرم‌سازی استفاده شود (سیستم این جداسازی را اجبار می‌کند). پاسخ خودکار
        به‌صورت پیش‌فرض خاموش است و فقط در ساعات کاری (۹ تا ۲۱ به‌وقت تهران) و با محدودیت نرخ ارسال می‌شود.
      </div>
      <div className="flex gap-2 flex-wrap">
        {TABS.map(([k, label]) => (
          <button
            key={k}
            className={tab === k ? "btn-primary" : "btn-ghost"}
            onClick={() => setTab(k)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "groups" && <GroupsTab />}
      {tab === "keywords" && <KeywordsTab />}
      {tab === "replies" && <RepliesTab />}
      {tab === "messages" && <MessagesTab />}
      {tab === "alerts" && <AlertsTab />}
    </div>
  );
}

// ── Listener picker + monitored groups ───────────────────────────────────────
function GroupsTab() {
  const { data: accounts, loading, reload } = useAsync(() => Accounts.list(), []);
  const [listenerId, setListenerId] = React.useState("");

  const listeners = (accounts || []).filter((a) => a.is_listener);
  const nonListeners = (accounts || []).filter((a) => !a.is_listener);

  const mark = async (id, val) => {
    try {
      await Api.setListener(id, val);
      toast.success(val ? "به‌عنوان شنونده تعیین شد" : "نقش شنونده برداشته شد");
      await reload();
      if (!val && listenerId === id) setListenerId("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  React.useEffect(() => {
    if (!listenerId && listeners.length) setListenerId(listeners[0].id);
  }, [listeners, listenerId]);

  if (loading) return <Spinner />;

  const selected = listeners.find((a) => a.id === listenerId);

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="font-bold">حساب‌های شنونده</div>
        {listeners.length === 0 && (
          <div className="text-slate-400 text-sm">هنوز حساب شنونده‌ای تعیین نشده است.</div>
        )}
        {listeners.map((a) => (
          <div key={a.id} className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div>
              <span className="font-bold">{a.name}</span>{" "}
              <span className="text-slate-400 text-xs">{a.phone || a.instance_id}</span>
            </div>
            <button className="btn-ghost text-red-400" onClick={() => mark(a.id, false)}>
              برداشتن نقش شنونده
            </button>
          </div>
        ))}
        <div className="flex items-center gap-2 pt-2">
          <select
            className="input"
            value=""
            onChange={(e) => e.target.value && mark(e.target.value, true)}
          >
            <option value="">+ تعیین حساب جدید به‌عنوان شنونده…</option>
            {nonListeners.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} — {a.phone || a.instance_id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {selected && (
        <div className="card space-y-2">
          <div className="flex items-center justify-between">
            <div className="font-bold">گروه‌های حساب: {selected.name}</div>
            <select className="input" value={listenerId} onChange={(e) => setListenerId(e.target.value)}>
              {listeners.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
          <MonitoredGroups account={selected} />
        </div>
      )}
    </div>
  );
}

function MonitoredGroups({ account }) {
  const { data, loading, error, reload } = useAsync(
    () => Api.availableGroups(account.id),
    [account.id]
  );

  const save = async (g, patch) => {
    try {
      await Api.upsertMonitored({
        listener_instance_id: account.instance_id,
        group_id: g.group_id,
        group_name: g.group_name,
        is_monitored: patch.is_monitored ?? g.is_monitored,
        auto_reply_enabled: patch.auto_reply_enabled ?? g.auto_reply_enabled,
        conversation_mode: patch.conversation_mode ?? g.conversation_mode,
      });
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  if (loading) return <Spinner />;
  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!data || data.length === 0)
    return <Empty label="گروهی یافت نشد. مطمئن شوید حساب شنونده عضو گروه‌هاست." />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-slate-400 border-b border-slate-700">
            <th className="text-right p-2">گروه</th>
            <th className="text-right p-2">پایش</th>
            <th className="text-right p-2">پاسخ خودکار</th>
            <th className="text-right p-2">حالت گفتگو</th>
          </tr>
        </thead>
        <tbody>
          {data.map((g) => (
            <tr key={g.group_id} className="border-b border-slate-800">
              <td className="p-2">{g.group_name || g.group_id}</td>
              <td className="p-2">
                <input
                  type="checkbox"
                  checked={g.is_monitored}
                  onChange={(e) => save(g, { is_monitored: e.target.checked })}
                />
              </td>
              <td className="p-2">
                <input
                  type="checkbox"
                  checked={g.auto_reply_enabled}
                  disabled={!g.is_monitored}
                  onChange={(e) => save(g, { auto_reply_enabled: e.target.checked })}
                />
              </td>
              <td className="p-2">
                <select
                  className="input"
                  value={g.conversation_mode}
                  disabled={!g.is_monitored}
                  onChange={(e) => save(g, { conversation_mode: e.target.value })}
                >
                  <option value="off">خاموش</option>
                  <option value="predefined">از پیش‌تعریف‌شده</option>
                  <option value="ai">هوش مصنوعی</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Keywords manager ─────────────────────────────────────────────────────────
function KeywordsTab() {
  const { data, loading, reload } = useAsync(() => Api.keywords(), []);
  const [word, setWord] = React.useState("");
  const [kind, setKind] = React.useState("trigger");

  const add = async () => {
    if (!word.trim()) return;
    try {
      await Api.createKeyword({ word: word.trim(), kind, active: true });
      setWord("");
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };
  const remove = async (id) => {
    if (!(await confirmDialog("حذف کلمه کلیدی؟"))) return;
    try {
      await Api.removeKeyword(id);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-3">
      <div className="card flex items-end gap-2 flex-wrap">
        <div className="flex-1 min-w-[160px]">
          <label className="text-xs text-slate-400">کلمه کلیدی</label>
          <input className="input w-full" value={word} onChange={(e) => setWord(e.target.value)}
                 placeholder="مثلاً قیمت" />
        </div>
        <div>
          <label className="text-xs text-slate-400">نوع</label>
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="trigger">محرک (تشخیص/پاسخ)</option>
            <option value="forbidden">ممنوعه (هشدار به مدیر)</option>
          </select>
        </div>
        <button className="btn-primary" onClick={add}>+ افزودن</button>
      </div>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty label="کلمه کلیدی‌ای ثبت نشده است." />}
      {data && data.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">کلمه</th>
                <th className="text-right p-2">نوع</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((k) => (
                <tr key={k.id} className="border-b border-slate-800">
                  <td className="p-2 font-bold">{k.word}</td>
                  <td className="p-2">
                    {k.kind === "forbidden" ? (
                      <span className="text-red-400">ممنوعه</span>
                    ) : (
                      <span className="text-emerald-400">محرک</span>
                    )}
                  </td>
                  <td className="p-2 text-left">
                    <button className="btn-ghost text-red-400" onClick={() => remove(k.id)}>حذف</button>
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

// ── Predefined replies ───────────────────────────────────────────────────────
function RepliesTab() {
  const { data, loading, reload } = useAsync(() => Api.replies(), []);
  const { data: keywords } = useAsync(() => Api.keywords(), []);
  const [text, setText] = React.useState("");
  const [keywordId, setKeywordId] = React.useState("");

  const triggers = (keywords || []).filter((k) => k.kind === "trigger");

  const add = async () => {
    if (!text.trim()) return;
    try {
      await Api.createReply({ reply_text: text.trim(), keyword_id: keywordId || null, active: true });
      setText("");
      setKeywordId("");
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };
  const remove = async (id) => {
    if (!(await confirmDialog("حذف پاسخ؟"))) return;
    try {
      await Api.removeReply(id);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const wordFor = (id) => triggers.find((k) => k.id === id)?.word;

  return (
    <div className="space-y-3">
      <div className="card space-y-2">
        <div className="text-sm text-slate-300">
          پاسخ‌های از پیش‌تعریف‌شده وقتی «حالت گفتگو» گروه روی «از پیش‌تعریف‌شده» باشد استفاده می‌شوند.
          پاسخ بدون کلمه کلیدی، پاسخ پیش‌فرض است.
        </div>
        <div className="flex items-end gap-2 flex-wrap">
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs text-slate-400">متن پاسخ</label>
            <input className="input w-full" value={text} onChange={(e) => setText(e.target.value)}
                   placeholder="مثلاً برای قیمت لطفاً خصوصی پیام دهید" />
          </div>
          <div>
            <label className="text-xs text-slate-400">کلمه کلیدی (اختیاری)</label>
            <select className="input" value={keywordId} onChange={(e) => setKeywordId(e.target.value)}>
              <option value="">پاسخ پیش‌فرض</option>
              {triggers.map((k) => (
                <option key={k.id} value={k.id}>{k.word}</option>
              ))}
            </select>
          </div>
          <button className="btn-primary" onClick={add}>+ افزودن</button>
        </div>
      </div>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty label="پاسخی ثبت نشده است." />}
      {data && data.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">متن</th>
                <th className="text-right p-2">کلمه کلیدی</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="border-b border-slate-800">
                  <td className="p-2">{r.reply_text}</td>
                  <td className="p-2">{r.keyword_id ? wordFor(r.keyword_id) || "—" : "پیش‌فرض"}</td>
                  <td className="p-2 text-left">
                    <button className="btn-ghost text-red-400" onClick={() => remove(r.id)}>حذف</button>
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

// ── Captured messages ────────────────────────────────────────────────────────
function MessagesTab() {
  const { data: monitored } = useAsync(() => Api.monitored(), []);
  const [groupId, setGroupId] = React.useState("");
  const { data, loading, reload } = useAsync(
    () => Api.messages(groupId ? { group_id: groupId } : {}),
    [groupId]
  );

  return (
    <div className="space-y-3">
      <div className="card flex items-center gap-2">
        <label className="text-sm text-slate-400">فیلتر گروه:</label>
        <select className="input" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">همه گروه‌ها</option>
          {(monitored || []).map((m) => (
            <option key={m.id} value={m.group_id}>{m.group_name || m.group_id}</option>
          ))}
        </select>
        <button className="btn-ghost" onClick={reload}>بروزرسانی</button>
      </div>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty label="پیامی ثبت نشده است." />}
      {data && data.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">فرستنده</th>
                <th className="text-right p-2">پیام</th>
                <th className="text-right p-2">کلمات محرک</th>
                <th className="text-right p-2">وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {data.map((m) => (
                <tr key={m.id} className="border-b border-slate-800">
                  <td className="p-2">
                    <div>{m.sender_name || "—"}</div>
                    <div className="text-xs text-slate-500">{m.group_name}</div>
                  </td>
                  <td className="p-2 max-w-[360px]">
                    {m.is_voice ? (
                      <div>
                        🎤 <span className="text-slate-400 text-xs">پیام صوتی</span>
                        {m.transcription ? (
                          <div className="text-slate-300">{m.transcription}</div>
                        ) : (
                          <div className="text-slate-500 text-xs">
                            {m.transcription_status === "pending" && "در حال رونویسی…"}
                            {m.transcription_status === "failed" && "رونویسی ناموفق"}
                          </div>
                        )}
                      </div>
                    ) : (
                      <span>{m.text || "—"}</span>
                    )}
                  </td>
                  <td className="p-2 text-emerald-400">{m.matched_keywords || "—"}</td>
                  <td className="p-2">
                    {m.flagged_forbidden && <span className="text-red-400 me-1">🚩 ممنوعه</span>}
                    {m.replied && <span className="text-sky-400">✅ پاسخ داده شد</span>}
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

// ── Admin forbidden-word alerts ──────────────────────────────────────────────
function AlertsTab() {
  const { data, loading, reload } = useAsync(() => Api.alerts(), []);

  const markRead = async (id) => {
    try {
      await Api.markAlertRead(id);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-3">
      <div className="card text-sm text-slate-300 bg-red-500/10 border-red-500/30">
        کلمات ممنوعه/حساس در گروه‌های پایش‌شده اینجا فهرست می‌شوند (هیچ پیام خودکاری ارسال نمی‌شود).
      </div>
      {loading && <Spinner />}
      {data && data.length === 0 && <Empty label="هشداری ثبت نشده است." />}
      {data && data.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">گروه</th>
                <th className="text-right p-2">فرستنده</th>
                <th className="text-right p-2">کلمه</th>
                <th className="text-right p-2">پیام</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id} className={"border-b border-slate-800 " + (a.is_read ? "opacity-50" : "")}>
                  <td className="p-2">{a.group_name || a.group_id}</td>
                  <td className="p-2">{a.sender_name || a.sender}</td>
                  <td className="p-2 text-red-400 font-bold">{a.word}</td>
                  <td className="p-2 max-w-[320px]">{a.message_text}</td>
                  <td className="p-2 text-left">
                    {!a.is_read && (
                      <button className="btn-ghost" onClick={() => markRead(a.id)}>خوانده شد</button>
                    )}
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
