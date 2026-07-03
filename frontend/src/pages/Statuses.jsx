import React from "react";
import { Statuses as Api } from "../api.js";

export default function Statuses() {
  const [tab, setTab] = React.useState("text");
  const [text, setText] = React.useState("");
  const [bg, setBg] = React.useState("#25D366");
  const [imageUrl, setImageUrl] = React.useState("");
  const [caption, setCaption] = React.useState("");
  const [result, setResult] = React.useState(null);
  const [busy, setBusy] = React.useState(false);

  const sendText = async () => {
    if (!text) return alert("متن لازم است");
    setBusy(true);
    try {
      setResult(await Api.sendText(text, bg, null));
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const sendImage = async () => {
    if (!imageUrl) return alert("آدرس تصویر لازم است");
    setBusy(true);
    try {
      setResult(await Api.sendImage(imageUrl, caption, null));
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 max-w-xl">
      <h2 className="text-2xl font-bold">استوری واتس‌اپ</h2>
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
    </div>
  );
}
