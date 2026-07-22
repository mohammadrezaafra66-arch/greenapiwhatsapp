import React from "react";
import { Statuses as Api, Accounts as AccApi } from "../api.js";
import { toast } from "../ui/toast.jsx";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

const PERSIAN_DAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
const STATUS_TYPE_LABELS = {
  intro: "معرفی مجموعه",
  special_offer: "پیشنهاد ویژه",
  custom: "متن دلخواه",
};

// Green API incoming-status fields vary by type/plan — read defensively.
function fmtTime(ts) {
  if (!ts) return "—";
  let ms = Number(ts);
  if (!ms) return String(ts);
  if (ms < 1e12) ms *= 1000; // seconds → ms
  try {
    return new Date(ms).toLocaleString("fa-IR");
  } catch {
    return String(ts);
  }
}

function statusSender(s) {
  return s.senderName || s.senderContactName || s.chatId || s.senderId || s.sender || "—";
}
function statusType(s) {
  return s.type || s.typeMessage || s.statusType || "—";
}
function statusContent(s) {
  return s.textStatus || s.text || s.caption || s.message || s.urlFile || s.downloadUrl || "";
}

function IncomingView({ data, loading, onRefresh, onAnalyzeToday, analyzingToday, onAnalyzeOne }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-400">
          {data?.account ? `حساب: ${data.account}` : "استوری‌های دریافتی"}
          {data && data.count != null ? ` · ${Number(data.count).toLocaleString("fa-IR")} مورد` : ""}
        </p>
        <div className="flex items-center gap-2">
          <button className="btn-primary text-xs" disabled={analyzingToday} onClick={onAnalyzeToday}>
            {analyzingToday ? "در حال تحلیل..." : "🧠 تحلیل همه استوری‌های امروز"}
          </button>
          <button className="btn-secondary text-xs" disabled={loading} onClick={onRefresh}>
            {loading ? "در حال بارگذاری..." : "🔄 تازه‌سازی"}
          </button>
        </div>
      </div>

      {loading && !data && <p className="text-slate-500 text-sm">در حال بارگذاری...</p>}

      {data?.error && (
        <div className="card bg-amber-500/10 border-amber-500/30 text-amber-200 text-sm">⚠️ {data.error}</div>
      )}

      {data && !data.error && (data.statuses || []).length === 0 && (
        <p className="text-slate-500 text-sm">استوری دریافتی‌ای وجود ندارد.</p>
      )}

      {data && (data.statuses || []).length > 0 && (
        <div className="space-y-2">
          {data.statuses.map((s, i) => {
            const content = statusContent(s);
            return (
              <div key={s.idMessage || s.receiptId || i} className="card space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-sm truncate">{statusSender(s)}</span>
                  <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40 whitespace-nowrap">
                    {statusType(s)}
                  </span>
                </div>
                <p className="text-xs text-slate-500">{fmtTime(s.timestamp || s.time)}</p>
                {content &&
                  (/^https?:\/\//.test(content) ? (
                    <a href={content} target="_blank" rel="noreferrer" className="text-sky-400 text-xs underline break-all">
                      {content}
                    </a>
                  ) : (
                    <p className="text-sm text-slate-200 whitespace-pre-line break-words">{content}</p>
                  ))}
                <div className="flex items-center gap-2 pt-1">
                  <button className="btn-secondary text-xs" onClick={() => onAnalyzeOne(s.row_id)}>
                    🤖 تحلیل با هوش مصنوعی
                  </button>
                  {s.analyzed && <span className="text-emerald-400 text-xs">✓ تحلیل‌شده</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// V40 PART 4 — «تحلیل محصولات استوری‌ها»: analyzed stories with product, in/out-of-assistant badge,
// AI confidence, and a thumbnail of the LOCALLY-persisted image (never an expiring WhatsApp link).
function AnalysisView({ data, loading, onRefresh, onAnalyzeToday, analyzingToday }) {
  const items = data?.items || [];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-400">
          تحلیل محصولات استوری‌ها{data && data.count != null ? ` · ${Number(data.count).toLocaleString("fa-IR")} مورد` : ""}
        </p>
        <div className="flex items-center gap-2">
          <button className="btn-primary text-xs" disabled={analyzingToday} onClick={onAnalyzeToday}>
            {analyzingToday ? "در حال تحلیل..." : "🧠 تحلیل همه استوری‌های امروز"}
          </button>
          <button className="btn-secondary text-xs" disabled={loading} onClick={onRefresh}>
            {loading ? "در حال بارگذاری..." : "🔄 تازه‌سازی"}
          </button>
        </div>
      </div>

      {data?.error && (
        <div className="card bg-amber-500/10 border-amber-500/30 text-amber-200 text-sm">⚠️ {data.error}</div>
      )}
      {!loading && items.length === 0 && !data?.error && (
        <p className="text-slate-500 text-sm">هنوز استوری تحلیل‌شده‌ای وجود ندارد. از تب «استوری‌های دریافتی» تحلیل را اجرا کنید.</p>
      )}

      {items.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm text-right">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="p-2">همکار/مخاطب</th>
                <th className="p-2">شماره/اکانت</th>
                <th className="p-2">متن استاتوس</th>
                <th className="p-2">عکس/لینک استاتوس</th>
                <th className="p-2">محصول تشخیص‌داده‌شده</th>
                <th className="p-2">برچسب</th>
                <th className="p-2">میزان اطمینان</th>
                <th className="p-2">تاریخ و ساعت</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-b border-slate-800 align-top">
                  <td className="p-2 font-bold">{r.contact_name}</td>
                  <td className="p-2 text-slate-300">{r.phone || "—"}</td>
                  <td className="p-2 text-slate-300 max-w-xs truncate">{r.status_text || "—"}</td>
                  <td className="p-2">
                    {r.thumbnail_url ? (
                      <div className="space-y-1">
                        <img src={Api.mediaUrl(r.story_id)} alt="story"
                          className="w-16 h-16 object-cover rounded border border-slate-700" />
                        {r.detected_product && (
                          <p className="text-[10px] text-slate-400">تشخیص AI: {r.detected_product}</p>
                        )}
                      </div>
                    ) : (
                      <span className="text-slate-600 text-xs">—</span>
                    )}
                  </td>
                  <td className="p-2">{r.detected_product || <span className="text-slate-600">—</span>}</td>
                  <td className="p-2">
                    <span className={`badge text-xs ${r.in_assistant ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-amber-500/20 text-amber-300 border-amber-500/40"}`}>
                      {r.assistant_status}
                    </span>
                  </td>
                  <td className="p-2 text-slate-300">
                    {r.ai_confidence != null ? `${Math.round(r.ai_confidence * 100)}%` : "—"}
                  </td>
                  <td className="p-2 text-slate-400 text-xs whitespace-nowrap">{r.analyzed_shamsi || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function HistoryView({ data, loading, onRefresh }) {
  const truncate = (s) => {
    const str = String(s || "");
    return str.length > 60 ? str.slice(0, 60) + "…" : str;
  };
  const statuses = data?.statuses || [];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-400">
          {data?.account ? `حساب: ${data.account}` : "تاریخچه استوری"}
        </p>
        <button className="btn-secondary text-xs" disabled={loading} onClick={onRefresh}>
          {loading ? "در حال بارگذاری..." : "🔄 تازه‌سازی"}
        </button>
      </div>

      {loading && !data && <p className="text-slate-500 text-sm">در حال بارگذاری...</p>}

      {data?.error && (
        <div className="card bg-amber-500/10 border-amber-500/30 text-amber-200 text-sm">⚠️ {data.error}</div>
      )}

      {data && !data.error && statuses.length === 0 && (
        <p className="text-slate-500 text-sm">استوری منتشرشده‌ای یافت نشد.</p>
      )}

      {data && !data.error && statuses.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-right">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="py-2 px-2 font-medium whitespace-nowrap">زمان</th>
                <th className="py-2 px-2 font-medium whitespace-nowrap">نوع</th>
                <th className="py-2 px-2 font-medium">محتوا</th>
                <th className="py-2 px-2 font-medium whitespace-nowrap">تعداد گیرنده</th>
              </tr>
            </thead>
            <tbody>
              {statuses.map((s, i) => {
                const content = s.textMessage || s.extendedTextMessage?.text || s.caption || "—";
                const recipients = s.extendedTextMessage?.participants?.length ?? "—";
                return (
                  <tr key={s.idMessage || i} className="border-b border-slate-800">
                    <td className="py-2 px-2 text-slate-400 whitespace-nowrap">{fmtTime(s.timestamp)}</td>
                    <td className="py-2 px-2 whitespace-nowrap">{s.typeMessage || "—"}</td>
                    <td className="py-2 px-2 text-slate-200 break-words">{truncate(content)}</td>
                    <td className="py-2 px-2 whitespace-nowrap">{recipients === "—" ? "—" : fa(recipients)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RoadmapView({ data, loading, onRefresh }) {
  const rows = data || [];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-400">برنامه آینده استوری</p>
        <button className="btn-secondary text-xs" disabled={loading} onClick={onRefresh}>
          {loading ? "در حال بارگذاری..." : "🔄 تازه‌سازی"}
        </button>
      </div>

      {loading && data === null && <p className="text-slate-500 text-sm">در حال بارگذاری...</p>}

      {data !== null && rows.length === 0 && (
        <div className="card bg-sky-500/10 border-sky-500/30 text-sky-200 text-sm">
          هیچ برنامه استوری‌ای برای این حساب تنظیم نشده. از صفحه «برنامه استوری» می‌توانید اضافه کنید.
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-right">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="py-2 px-2 font-medium whitespace-nowrap">نام</th>
                <th className="py-2 px-2 font-medium whitespace-nowrap">نوع</th>
                <th className="py-2 px-2 font-medium whitespace-nowrap">اجرای بعدی (شمسی)</th>
                <th className="py-2 px-2 font-medium">روزها/تاریخ‌ها</th>
                <th className="py-2 px-2 font-medium">ساعت‌ها</th>
                <th className="py-2 px-2 font-medium whitespace-nowrap">وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const typeLabel = STATUS_TYPE_LABELS[r.status_type] || r.status_type || "—";
                let when = "—";
                if (r.specific_dates && r.specific_dates.length) {
                  when = r.specific_dates.join("،");
                } else if (r.days_of_week && r.days_of_week.length) {
                  when = r.days_of_week.map((d) => PERSIAN_DAYS[d] ?? d).join("،");
                }
                const times = (r.times && r.times.length) ? r.times.join("،") : "—";
                return (
                  <tr key={r.id || i} className="border-b border-slate-800">
                    <td className="py-2 px-2 whitespace-nowrap">{r.name || "—"}</td>
                    <td className="py-2 px-2 whitespace-nowrap">{typeLabel}</td>
                    <td className="py-2 px-2 text-slate-400 whitespace-nowrap">{r.next_run_shamsi || "—"}</td>
                    <td className="py-2 px-2 text-slate-200 break-words">{when}</td>
                    <td className="py-2 px-2 text-slate-200 whitespace-nowrap">{times}</td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      {r.is_active ? (
                        <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">فعال</span>
                      ) : (
                        <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40">غیرفعال</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Statuses() {
  const [mainTab, setMainTab] = React.useState("mine"); // mine | incoming | history | roadmap
  const [tab, setTab] = React.useState("image"); // image | text | voice (within "mine"); media default

  // Accounts + selected account (used by incoming/history/roadmap tabs)
  const [accounts, setAccounts] = React.useState([]);
  const [selectedAccount, setSelectedAccount] = React.useState("");
  const [text, setText] = React.useState("");
  const [bg, setBg] = React.useState("#25D366");
  const [imageUrl, setImageUrl] = React.useState("");
  const [caption, setCaption] = React.useState("");
  const [voiceUrl, setVoiceUrl] = React.useState("");
  const [participantsText, setParticipantsText] = React.useState(""); // V14 F19 targeted
  const [result, setResult] = React.useState(null);
  const [busy, setBusy] = React.useState(false);

  // null = public to all contacts; otherwise a list of phones.
  const parseParticipants = () => {
    const arr = participantsText.split(/[\n,،]+/).map((s) => s.trim()).filter(Boolean);
    return arr.length ? arr : null;
  };

  // Incoming statuses (fetched on demand — no auto-poll, so a Green API 403
  // can't repeatedly trip the per-instance circuit breaker).
  const [incoming, setIncoming] = React.useState(null);
  const [incLoading, setIncLoading] = React.useState(false);

  // V40 PART 4 — analyzed-story product table.
  const [analysis, setAnalysis] = React.useState(null);
  const [anaLoading, setAnaLoading] = React.useState(false);

  // Posted-status history + upcoming roadmap (per selected account).
  const [histData, setHistData] = React.useState(null);
  const [histLoading, setHistLoading] = React.useState(false);
  const [schedData, setSchedData] = React.useState(null);
  const [schedLoading, setSchedLoading] = React.useState(false);

  const loadIncoming = async () => {
    setIncLoading(true);
    try {
      setIncoming(await Api.incoming());
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      toast.error(msg);
      setIncoming({ statuses: [], error: msg });
    } finally {
      setIncLoading(false);
    }
  };

  const loadAnalysis = async () => {
    setAnaLoading(true);
    try {
      setAnalysis(await Api.analysisList(selectedAccount));
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      toast.error(msg);
      setAnalysis({ items: [], error: msg });
    } finally {
      setAnaLoading(false);
    }
  };

  // V40 PART 3.4 — analyze every not-yet-analyzed story stored today (text + image, cached once).
  const [analyzingToday, setAnalyzingToday] = React.useState(false);
  const analyzeToday = async () => {
    setAnalyzingToday(true);
    try {
      const res = await Api.analyzeToday(selectedAccount);
      toast.success(res.message || "تحلیل انجام شد");
      if (mainTab === "analysis") loadAnalysis();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setAnalyzingToday(false);
    }
  };

  // V40 PART 3.3 — analyze ONE story from the received list (row_id attached by the backend).
  const analyzeOne = async (rowId) => {
    if (!rowId) return toast.info("این استوری هنوز ذخیره نشده — یک‌بار «تازه‌سازی» بزنید.");
    try {
      const res = await Api.analyzeStory(rowId);
      toast.success(res.detected_product
        ? `تشخیص AI: ${res.detected_product} (${res.assistant_status})`
        : "محصولی در این استوری تشخیص داده نشد");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const loadHistory = async (accId) => {
    if (!accId) return;
    setHistLoading(true);
    try {
      setHistData(await Api.history(accId));
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      toast.error(msg);
      setHistData({ statuses: [], error: msg });
    } finally {
      setHistLoading(false);
    }
  };

  const loadScheduled = async (accId) => {
    if (!accId) return;
    setSchedLoading(true);
    try {
      setSchedData(await Api.scheduled(accId));
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      toast.error(msg);
      setSchedData([]);
    } finally {
      setSchedLoading(false);
    }
  };

  // Load accounts once on mount.
  React.useEffect(() => {
    AccApi.list().then((a) => {
      setAccounts(a || []);
      const d = (a || []).find((x) => x.is_default) || (a || [])[0];
      if (d) setSelectedAccount(d.id);
    });
  }, []);

  React.useEffect(() => {
    if (mainTab === "incoming" && incoming === null) loadIncoming();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainTab]);

  // (Re)load history/roadmap/analysis when their tab becomes active or the account changes.
  React.useEffect(() => {
    if (mainTab === "history") loadHistory(selectedAccount);
    if (mainTab === "roadmap") loadScheduled(selectedAccount);
    if (mainTab === "analysis") loadAnalysis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainTab, selectedAccount]);

  const sendText = async () => {
    if (!text) return toast.error("متن لازم است");
    setBusy(true);
    try {
      setResult(await Api.sendText(text, bg, null, parseParticipants()));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const sendImage = async () => {
    if (!imageUrl) return toast.error("آدرس تصویر لازم است");
    setBusy(true);
    try {
      setResult(await Api.sendImage(imageUrl, caption, null, parseParticipants()));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const sendVoice = async () => {
    if (!voiceUrl) return toast.error("آدرس فایل صوتی لازم است");
    setBusy(true);
    try {
      setResult(await Api.sendVoice(voiceUrl, null, parseParticipants()));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`space-y-4 ${mainTab === "analysis" ? "max-w-6xl" : "max-w-xl"}`}>
      <h2 className="text-2xl font-bold">استوری واتس‌اپ</h2>

      {/* Main tabs */}
      <div className="flex gap-2 flex-wrap items-center">
        <button className={mainTab === "mine" ? "btn-primary" : "btn-secondary"} onClick={() => setMainTab("mine")}>استوری‌های من</button>
        <button className={mainTab === "incoming" ? "btn-primary" : "btn-secondary"} onClick={() => setMainTab("incoming")}>استوری‌های دریافتی</button>
        <button className={mainTab === "analysis" ? "btn-primary" : "btn-secondary"} onClick={() => setMainTab("analysis")}>تحلیل محصولات استوری‌ها</button>
        <button className={mainTab === "history" ? "btn-primary" : "btn-secondary"} onClick={() => setMainTab("history")}>تاریخچه استوری</button>
        <button className={mainTab === "roadmap" ? "btn-primary" : "btn-secondary"} onClick={() => setMainTab("roadmap")}>برنامه آینده</button>

        {(mainTab === "incoming" || mainTab === "history" || mainTab === "roadmap" || mainTab === "analysis") && (
          <select
            className="input w-auto"
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        )}
      </div>

      {mainTab === "mine" ? (
        <>
          <p className="text-sm text-slate-400">استوری روی همه حساب‌های فعال منتشر می‌شود.</p>

          <div className="card bg-amber-500/10 border-amber-500/30 text-amber-200 text-sm">
            💡 استوری عکس‌دار معمولاً بازدید بیشتری از استوری متنی می‌گیرد. برای تبلیغات، «عکس با کپشن» را انتخاب کنید.
          </div>

          <div className="flex gap-2">
            <button className={tab === "image" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("image")}>عکس</button>
            <button className={tab === "text" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("text")}>متنی</button>
            <button className={tab === "voice" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("voice")}>صوتی</button>
          </div>

          <div className="card space-y-2">
            <label className="label mb-0">ارسال فقط به افراد خاص (اختیاری)</label>
            <textarea className="input h-16" placeholder="شماره‌ها را با کاما یا خط جدید وارد کنید — خالی = عمومی برای همه مخاطبین"
              value={participantsText} onChange={(e) => setParticipantsText(e.target.value)} />
          </div>

          {tab === "text" ? (
            <div className="card space-y-3">
              <div><label className="label">متن استوری</label><textarea className="input h-24" value={text} onChange={(e) => setText(e.target.value)} /></div>
              <div className="flex items-center gap-3">
                <label className="label mb-0">رنگ پس‌زمینه</label>
                <input type="color" value={bg} onChange={(e) => setBg(e.target.value)} className="h-9 w-16 bg-transparent" />
                <span className="font-mono text-sm">{bg}</span>
              </div>
              <button className="btn-primary w-full" disabled={busy} onClick={sendText}>{busy ? "..." : "انتشار استوری متنی"}</button>
            </div>
          ) : tab === "voice" ? (
            <div className="card space-y-3">
              <div><label className="label">آدرس فایل صوتی (mp3/ogg)</label><input className="input" value={voiceUrl} onChange={(e) => setVoiceUrl(e.target.value)} placeholder="https://…/voice.mp3" /></div>
              <p className="text-xs text-slate-500">فایل صوتی را ابتدا در «فایل‌ها» آپلود کنید و لینک آن را اینجا بگذارید.</p>
              <button className="btn-primary w-full" disabled={busy} onClick={sendVoice}>{busy ? "..." : "انتشار استوری صوتی"}</button>
            </div>
          ) : (
            <div className="card space-y-3">
              <div><label className="label">آدرس تصویر (لینک)</label><input className="input" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} /></div>
              <div><label className="label">توضیح تصویر (کپشن)</label><input className="input" value={caption} onChange={(e) => setCaption(e.target.value)} /></div>
              <button className="btn-primary w-full" disabled={busy} onClick={sendImage}>{busy ? "..." : "انتشار استوری تصویری"}</button>
            </div>
          )}

          {result && (
            <div className="card">
              <p className="text-sm text-slate-400 mb-2">ارسال به {result.sent_to} حساب:</p>
              <ul className="text-sm space-y-1">
                {result.results.map((r, i) => (
                  <li key={i} className="flex justify-between">
                    <span>{r.account}</span>
                    <span className={r.error ? "text-red-400" : "text-emerald-400 font-mono text-xs"}>{r.error || r.message_id || "ok"}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : mainTab === "incoming" ? (
        <IncomingView data={incoming} loading={incLoading} onRefresh={loadIncoming}
          onAnalyzeToday={analyzeToday} analyzingToday={analyzingToday} onAnalyzeOne={analyzeOne} />
      ) : mainTab === "analysis" ? (
        <AnalysisView data={analysis} loading={anaLoading} onRefresh={loadAnalysis}
          onAnalyzeToday={analyzeToday} analyzingToday={analyzingToday} />
      ) : mainTab === "history" ? (
        <HistoryView data={histData} loading={histLoading} onRefresh={() => loadHistory(selectedAccount)} />
      ) : (
        <RoadmapView data={schedData} loading={schedLoading} onRefresh={() => loadScheduled(selectedAccount)} />
      )}
    </div>
  );
}
