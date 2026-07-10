import React from "react";
import { Statuses as Api } from "../api.js";
import { toast } from "../ui/toast.jsx";

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

function IncomingView({ data, loading, onRefresh }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-400">
          {data?.account ? `حساب: ${data.account}` : "استوری‌های دریافتی"}
          {data && data.count != null ? ` · ${Number(data.count).toLocaleString("fa-IR")} مورد` : ""}
        </p>
        <button className="btn-secondary text-xs" disabled={loading} onClick={onRefresh}>
          {loading ? "در حال بارگذاری..." : "🔄 تازه‌سازی"}
        </button>
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
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Statuses() {
  const [mainTab, setMainTab] = React.useState("mine"); // mine | incoming
  const [tab, setTab] = React.useState("text"); // text | image (within "mine")
  const [text, setText] = React.useState("");
  const [bg, setBg] = React.useState("#25D366");
  const [imageUrl, setImageUrl] = React.useState("");
  const [caption, setCaption] = React.useState("");
  const [result, setResult] = React.useState(null);
  const [busy, setBusy] = React.useState(false);

  // Incoming statuses (fetched on demand — no auto-poll, so a Green API 403
  // can't repeatedly trip the per-instance circuit breaker).
  const [incoming, setIncoming] = React.useState(null);
  const [incLoading, setIncLoading] = React.useState(false);

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

  React.useEffect(() => {
    if (mainTab === "incoming" && incoming === null) loadIncoming();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainTab]);

  const sendText = async () => {
    if (!text) return toast.error("متن لازم است");
    setBusy(true);
    try {
      setResult(await Api.sendText(text, bg, null));
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
      setResult(await Api.sendImage(imageUrl, caption, null));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 max-w-xl">
      <h2 className="text-2xl font-bold">استوری واتس‌اپ</h2>

      {/* Main tabs */}
      <div className="flex gap-2">
        <button className={mainTab === "mine" ? "btn-primary" : "btn-secondary"} onClick={() => setMainTab("mine")}>استوری‌های من</button>
        <button className={mainTab === "incoming" ? "btn-primary" : "btn-secondary"} onClick={() => setMainTab("incoming")}>استوری‌های دریافتی</button>
      </div>

      {mainTab === "mine" ? (
        <>
          <p className="text-sm text-slate-400">استوری روی همه حساب‌های فعال منتشر می‌شود.</p>

          <div className="flex gap-2">
            <button className={tab === "text" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("text")}>متنی</button>
            <button className={tab === "image" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("image")}>تصویری</button>
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
          ) : (
            <div className="card space-y-3">
              <div><label className="label">آدرس تصویر (لینک)</label><input className="input" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} /></div>
              <div><label className="label">توضیح تصویر</label><input className="input" value={caption} onChange={(e) => setCaption(e.target.value)} /></div>
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
      ) : (
        <IncomingView data={incoming} loading={incLoading} onRefresh={loadIncoming} />
      )}
    </div>
  );
}
