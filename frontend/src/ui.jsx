import React from "react";

export const STATUS_FA = {
  active: "متصل ✅",
  banned: "مسدود 🚫",
  disconnected: "قطع 🔌",
  pending: "در انتظار اتصال ⏳",
  // V36 — instance removed from the Green API console (terminal, unrecoverable).
  green_api_deleted: "حذف‌شده در Green API 🗑️",
  draft: "پیش‌نویس",
  running: "در حال اجرا",
  paused: "متوقف",
  completed: "تکمیل شده",
  failed: "ناموفق",
};

const STATUS_COLOR = {
  active: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  banned: "bg-red-500/20 text-red-300 border-red-500/40",
  disconnected: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  pending: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  green_api_deleted: "bg-red-500/20 text-red-300 border-red-500/40",
  running: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  paused: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  completed: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  failed: "bg-red-500/20 text-red-300 border-red-500/40",
  draft: "bg-slate-500/20 text-slate-300 border-slate-500/40",
};

export function Badge({ status }) {
  const cls = STATUS_COLOR[status] || STATUS_COLOR.draft;
  return <span className={`badge ${cls}`}>{STATUS_FA[status] || status}</span>;
}

export function Progress({ value, max, color = "bg-sky-500" }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="w-full bg-slate-700 rounded-full h-2">
      <div className={`${color} h-2 rounded-full`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Spinner({ label = "در حال بارگذاری..." }) {
  return <p className="text-slate-500 text-sm">{label}</p>;
}

export function Empty({ label = "موردی یافت نشد." }) {
  return <p className="text-slate-500 text-sm">{label}</p>;
}

export function Modal({ title, onClose, children, wide = false }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className={`card w-full ${wide ? "max-w-2xl" : "max-w-md"} max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-lg">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-xl leading-none">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function useAsync(fn, deps = []) {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  const reload = React.useCallback(() => {
    setLoading(true);
    fn()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  React.useEffect(() => {
    reload();
  }, [reload]);

  return { data, loading, error, reload, setData };
}
