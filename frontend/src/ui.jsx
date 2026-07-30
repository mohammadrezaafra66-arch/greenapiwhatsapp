import React from "react";

export const STATUS_FA = {
  active: "متصل ✅",
  banned: "مسدود 🚫",
  disconnected: "قطع 🔌",
  pending: "در انتظار اتصال ⏳",
  // V36 — instance removed from the provider console (terminal, unrecoverable).
  green_api_deleted: "حذف‌شده در سرویس 🗑️",
  draft: "پیش‌نویس",
  running: "در حال اجرا",
  paused: "متوقف",
  completed: "تکمیل شده",
  failed: "ناموفق",
};

// Light-theme status colors. Green = healthy, red = danger, amber = warning,
// sky = neutral-info, slate = idle. Soft tinted background + readable text.
const STATUS_COLOR = {
  active: "bg-brand-light text-brand border-brand/30",
  banned: "bg-red-50 text-red-700 border-red-200",
  disconnected: "bg-slate-100 text-slate-600 border-slate-300",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  green_api_deleted: "bg-red-50 text-red-700 border-red-200",
  running: "bg-brand-light text-brand border-brand/30",
  paused: "bg-amber-50 text-amber-700 border-amber-200",
  completed: "bg-sky-50 text-sky-700 border-sky-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  draft: "bg-slate-100 text-slate-600 border-slate-300",
};

export function Badge({ status }) {
  const cls = STATUS_COLOR[status] || STATUS_COLOR.draft;
  return <span className={`badge ${cls}`}>{STATUS_FA[status] || status}</span>;
}

export function Progress({ value, max, color = "bg-brand" }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="w-full bg-line rounded-full h-2">
      <div className={`${color} h-2 rounded-full`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Standardized action button ────────────────────────────────────────────────
// One component for every action. size: sm(32) | md(40) | lg(48). variant:
// primary | secondary | danger | ghost. `loading` shows a spinner, sets aria-busy,
// and blocks re-clicks so a request can't be double-submitted.
const BTN_SIZE = { sm: "btn-sm", md: "btn-md", lg: "btn-lg" };
const BTN_VARIANT = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  danger: "btn-danger",
  ghost: "btn-ghost",
};

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  icon = null,
  type = "button",
  className = "",
  ...rest
}) {
  const cls = [
    BTN_VARIANT[variant] || BTN_VARIANT.primary,
    BTN_SIZE[size] || BTN_SIZE.md,
    loading ? "btn-loading" : "",
    className,
  ].filter(Boolean).join(" ");
  return (
    <button type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Spinner inline /> : icon}
      {children}
    </button>
  );
}

export function Spinner({ label = "در حال بارگذاری...", inline = false }) {
  const ring = (
    <span
      className={`inline-block w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin ${inline ? "" : "text-brand"}`}
      aria-hidden="true"
    />
  );
  if (inline) return ring;
  return (
    <span className="inline-flex items-center gap-2 text-muted text-sm">
      {ring}
      {label}
    </span>
  );
}

export function Empty({ label = "موردی یافت نشد." }) {
  return <p className="text-muted text-sm">{label}</p>;
}

export function Modal({ title, onClose, children, wide = false }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" dir="rtl">
      <div className={`card w-full ${wide ? "max-w-2xl" : "max-w-md"} max-h-[90vh] overflow-y-auto shadow-pop`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-lg text-ink">{title}</h3>
          <button onClick={onClose} aria-label="بستن" className="text-muted hover:text-ink text-xl leading-none">×</button>
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
