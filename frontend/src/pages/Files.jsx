import React from "react";
import { useNavigate } from "react-router-dom";
import { FilesApi as Api, Accounts } from "../api.js";
import { Spinner, Empty, useAsync } from "../ui.jsx";

export default function Files() {
  const navigate = useNavigate();
  const { data: accounts, loading: accLoading } = useAsync(() => Accounts.list(), []);
  const [accountId, setAccountId] = React.useState("");
  const [files, setFiles] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [lastUrl, setLastUrl] = React.useState("");
  const [dragOver, setDragOver] = React.useState(false);
  const inputRef = React.useRef(null);

  const loadFiles = React.useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      setFiles(await Api.list(id));
    } catch {
      setFiles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (accountId) loadFiles(accountId);
  }, [accountId, loadFiles]);

  const doUpload = async (file) => {
    if (!accountId) return alert("ابتدا یک حساب انتخاب کنید");
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await Api.upload(accountId, fd);
      setLastUrl(r.url);
      await loadFiles(accountId);
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) doUpload(file);
  };

  const copy = (url) => {
    navigator.clipboard?.writeText(url);
    alert("کپی شد");
  };

  const useInCampaign = (url) => {
    localStorage.setItem("afrakala_prefill_image_url", url);
    navigate("/campaigns");
  };

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">مدیریت فایل‌ها</h2>

      <div className="card">
        <label className="label">حساب</label>
        {accLoading ? (
          <Spinner />
        ) : (
          <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">— یک حساب انتخاب کنید —</option>
            {accounts?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        )}
      </div>

      {accountId && (
        <>
          <div
            className={`card border-2 border-dashed text-center py-10 cursor-pointer transition-colors ${dragOver ? "border-brand bg-brand/10" : "border-slate-600"}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
          >
            <input ref={inputRef} type="file" className="hidden" onChange={(e) => doUpload(e.target.files?.[0])} />
            <p className="text-slate-300">{uploading ? "در حال آپلود..." : "فایل را اینجا رها کنید یا کلیک کنید"}</p>
            <p className="text-xs text-slate-500 mt-1">تصویر، ویدیو، سند و ...</p>
          </div>

          {lastUrl && (
            <div className="card space-y-2">
              <p className="text-sm text-emerald-300">آپلود موفق بود:</p>
              <div className="flex flex-wrap items-center gap-2">
                <input className="input flex-1 font-mono text-xs" value={lastUrl} readOnly />
                <button className="btn-secondary" onClick={() => copy(lastUrl)}>کپی</button>
                <button className="btn-primary" onClick={() => useInCampaign(lastUrl)}>این URL را در کمپین استفاده کن</button>
              </div>
            </div>
          )}

          <div className="card overflow-x-auto">
            <h3 className="font-bold mb-3">فایل‌های آپلودشده</h3>
            {loading && <Spinner />}
            {files && files.length === 0 && <Empty label="فایلی آپلود نشده است." />}
            {files && files.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 border-b border-slate-700">
                    <th className="text-right p-2">نام فایل</th>
                    <th className="text-right p-2">URL</th>
                    <th className="text-right p-2">تاریخ</th>
                    <th className="text-right p-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f) => (
                    <tr key={f.id} className="border-b border-slate-800">
                      <td className="p-2">{f.filename}</td>
                      <td className="p-2 font-mono text-xs truncate max-w-xs">{f.url}</td>
                      <td className="p-2 text-xs text-slate-500">{f.uploaded_at?.slice(0, 16)}</td>
                      <td className="p-2">
                        <div className="flex gap-2">
                          <button className="text-sky-400 hover:underline" onClick={() => copy(f.url)}>کپی</button>
                          <button className="text-brand hover:underline" onClick={() => useInCampaign(f.url)}>کمپین</button>
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
    </div>
  );
}
