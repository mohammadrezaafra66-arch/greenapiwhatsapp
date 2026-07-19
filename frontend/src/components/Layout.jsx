import React from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { IncidentsApi, Inbox as InboxApi, QueueApi } from "../api.js";

const fa = (n) => (n == null ? "" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

// V14 PART H — the new information architecture (7 groups, «ابزارها» dissolved).
// Every leaf points to an EXISTING route, so no bookmarked page 404s.
const NAV = [
  { label: "داشبورد", to: "/", icon: "🏠", end: true },
  {
    label: "ارسال پیام", icon: "📤", children: [
      { to: "/campaigns", label: "کمپین‌ها" },
      { to: "/wa-collections", label: "ارسال گروهی" },
      { to: "/send-queue", label: "صف ارسال", badgeKey: "queue" },
    ],
  },
  {
    label: "مخاطبان", icon: "👥", children: [
      { to: "/contacts", label: "مخاطبین" },
      { to: "/contact-groups", label: "دسته‌بندی مخاطبین" },
      { to: "/groups", label: "گروه‌های واتساپ" },
      { to: "/wa-collections", label: "مجموعه‌های گروهی" },
      { to: "/blacklist", label: "لیست سیاه" },
    ],
  },
  {
    label: "محتوا", icon: "✍️", children: [
      { to: "/templates", label: "قالب‌های پیام" },
      { to: "/button-auto-replies", label: "دکمه‌های تعاملی" },
      { to: "/statuses", label: "استوری‌ها" },
      { to: "/status-scheduler", label: "برنامه استوری" },
      { to: "/files", label: "فایل‌ها" },
      { to: "/content", label: "کارت تماس و موقعیت" },
      { to: "/advertising-links", label: "لینک‌های تبلیغاتی" },
    ],
  },
  {
    label: "گفتگوها", icon: "💬", children: [
      { to: "/inbox", label: "صندوق ورودی", badgeKey: "inbox" },
      { to: "/journals", label: "تاریخچه پیام‌ها" },
      { to: "/keyword-rules", label: "پاسخ خودکار" },
      { to: "/group-monitoring", label: "پایش گروه‌ها" },
      { to: "/calls", label: "تماس‌ها" },
    ],
  },
  {
    label: "شماره‌ها", icon: "📱", children: [
      { to: "/accounts", label: "حساب‌های واتساپ" },
      { to: "/telegram-accounts", label: "حساب‌های تلگرام" },
      { to: "/account-schedules", label: "زمان‌بندی حساب‌ها" },
      { to: "/protection", label: "محافظت و سلامت", badgeKey: "incidents", badgeRed: true },
      { to: "/warmup", label: "گرم‌سازی هوشمند" },
      { to: "/team-collaboration", label: "همکاری تیمی" },
      { to: "/partner-instances", label: "مدیریت پارتنر" },
    ],
  },
  {
    label: "گزارش‌ها", icon: "📊", children: [
      { to: "/reporting", label: "گزارش روزانه" },
      { to: "/products", label: "رصد محصولات" },
      { to: "/reporting", label: "بهترین ساعت ارسال" },
      { to: "/campaigns", label: "بازده کمپین (ROI)" },
    ],
  },
  { separator: true },
  {
    label: "تنظیمات", icon: "⚙️", children: [
      { to: "/ai-keys", label: "کلیدهای هوش مصنوعی" },
      { to: "/ai-settings", label: "تنظیمات هوش مصنوعی" },
      { to: "/capabilities", label: "قابلیت‌های Green API" },
      { to: "/join-links", label: "لینک‌های گروه و کانال" },
      { to: "/reporting", label: "شماره‌های اضطراری" },
    ],
  },
];

// Flat page list (+ synonyms) for the ⌘K palette.
const PAGES = [
  { to: "/", label: "داشبورد", syn: "خانه صفحه اصلی dashboard home" },
  { to: "/campaigns", label: "کمپین‌ها", syn: "ارسال پیام گروهی campaign بازده roi" },
  { to: "/send-queue", label: "صف ارسال", syn: "queue توقف اضطراری پاک کردن صف" },
  { to: "/contacts", label: "مخاطبین", syn: "contacts شماره‌ها" },
  { to: "/contact-groups", label: "دسته‌بندی مخاطبین", syn: "گروه مخاطبین segment" },
  { to: "/groups", label: "گروه‌های واتساپ", syn: "whatsapp groups مدیریت گروه افزودن عضو" },
  { to: "/wa-collections", label: "مجموعه‌های گروهی / ارسال گروهی", syn: "collections" },
  { to: "/blacklist", label: "لیست سیاه", syn: "blacklist مسدود opt-out" },
  { to: "/templates", label: "قالب‌های پیام", syn: "templates" },
  { to: "/button-auto-replies", label: "دکمه‌های تعاملی", syn: "buttons پاسخ خودکار دکمه" },
  { to: "/statuses", label: "استوری‌ها", syn: "status استوری صوتی هدفمند" },
  { to: "/status-scheduler", label: "برنامه استوری", syn: "schedule status" },
  { to: "/files", label: "فایل‌ها", syn: "files upload" },
  { to: "/content", label: "کارت تماس و موقعیت", syn: "contact card location موقعیت" },
  { to: "/advertising-links", label: "لینک‌های تبلیغاتی", syn: "advertising links telegram instagram promo" },
  { to: "/inbox", label: "صندوق ورودی", syn: "inbox پیام‌های دریافتی" },
  { to: "/journals", label: "تاریخچه پیام‌ها", syn: "journals history" },
  { to: "/keyword-rules", label: "پاسخ خودکار", syn: "keyword auto reply" },
  { to: "/group-monitoring", label: "پایش گروه‌ها", syn: "group monitor listener voice whisper شنونده صوتی رونویسی کلمه کلیدی ممنوعه" },
  { to: "/telegram-accounts", label: "حساب‌های تلگرام", syn: "telegram تلگرام اکانت qr اتصال" },
  { to: "/calls", label: "تماس‌ها", syn: "calls تماس بی‌پاسخ hot lead" },
  { to: "/accounts", label: "حساب‌های واتساپ", syn: "accounts شماره پروفایل" },
  { to: "/account-schedules", label: "زمان‌بندی حساب‌ها", syn: "schedule" },
  { to: "/protection", label: "محافظت و سلامت", syn: "yellowcard کارت زرد امنیت سلامت incident" },
  { to: "/warmup", label: "گرم‌سازی هوشمند", syn: "warmup warm up گرم سازی phrases" },
  { to: "/team-collaboration", label: "همکاری تیمی", syn: "team collaboration همکاری تیمی گرم سازی افراد واقعی cold account warmth log alerts" },
  { to: "/partner-instances", label: "مدیریت پارتنر", syn: "partner ساخت شماره qr" },
  { to: "/reporting", label: "گزارش روزانه", syn: "report بهترین ساعت شماره‌های اضطراری" },
  { to: "/products", label: "رصد محصولات", syn: "products محصول" },
  { to: "/ai-keys", label: "کلیدهای هوش مصنوعی", syn: "ai keys openai" },
  { to: "/ai-settings", label: "تنظیمات هوش مصنوعی", syn: "ai settings" },
  { to: "/capabilities", label: "قابلیت‌های Green API", syn: "capabilities method support پشتیبانی" },
  { to: "/join-links", label: "لینک‌های گروه و کانال", syn: "join links دعوت" },
];

const MOBILE_BAR = [
  { to: "/", label: "داشبورد", icon: "🏠", end: true },
  { to: "/campaigns", label: "ارسال", icon: "📤" },
  { to: "/inbox", label: "گفتگوها", icon: "💬" },
  { to: "/reporting", label: "گزارش‌ها", icon: "📊" },
];

const LS_COLLAPSED = "afrakala.sidebar.collapsed";
const LS_GROUP = (label) => `afrakala.nav.open.${label}`;

// Active-item styling: RIGHT-edge indicator bar + heavier font weight (never color alone).
function leafClass({ isActive }) {
  return `group flex items-center gap-2 pl-3 pr-2 py-2 rounded-lg text-sm min-h-[40px] transition-[background,color] duration-150 ease-out ${
    isActive
      ? "bg-brand/15 text-brand font-bold border-r-2 border-brand"
      : "text-slate-300 hover:bg-slate-800 border-r-2 border-transparent"
  }`;
}

function Badge({ n, red }) {
  if (!n) return null;
  return (
    <span className={`mr-auto badge text-xs ${red ? "bg-red-500/30 text-red-300 border-red-500/50" : "bg-amber-500/25 text-amber-200 border-amber-500/50"}`}>
      {fa(n)}
    </span>
  );
}

function NavGroup({ item, badges, collapsed }) {
  const location = useLocation();
  const childActive = item.children.some((c) => location.pathname === c.to);
  const stored = typeof localStorage !== "undefined" ? localStorage.getItem(LS_GROUP(item.label)) : null;
  const [open, setOpen] = React.useState(stored != null ? stored === "1" : childActive);

  React.useEffect(() => { if (childActive) setOpen(true); }, [childActive]);
  const toggle = () => setOpen((o) => { localStorage.setItem(LS_GROUP(item.label), o ? "0" : "1"); return !o; });

  const groupBadge = item.children.reduce((s, c) => s + (c.badgeKey ? (badges[c.badgeKey] || 0) : 0), 0);
  const groupRed = item.children.some((c) => c.badgeRed && badges[c.badgeKey]);

  if (collapsed) {
    // icon-rail: show the group icon with a tooltip; clicking jumps to the first child.
    const to = item.children[0]?.to || "/";
    return (
      <NavLink to={to} title={item.label} className={leafClass}>
        <span className="text-lg mx-auto relative">
          {item.icon}
          {groupBadge > 0 && <span className={`absolute -top-1 -left-1 w-2 h-2 rounded-full ${groupRed ? "bg-red-400" : "bg-amber-400"}`} />}
        </span>
      </NavLink>
    );
  }

  return (
    <div>
      <button onClick={toggle} aria-expanded={open}
        className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-sm min-h-[40px] transition-colors duration-150 ease-out ${childActive ? "text-brand font-bold" : "text-slate-300 hover:bg-slate-800"}`}>
        <span className="flex items-center gap-2">
          <span className="text-base">{item.icon}</span>
          <span>{item.label}</span>
        </span>
        <span className="flex items-center gap-1">
          {groupBadge > 0 && <span className={`badge text-xs ${groupRed ? "bg-red-500/30 text-red-300 border-red-500/50" : "bg-amber-500/25 text-amber-200 border-amber-500/50"}`}>{fa(groupBadge)}</span>}
          <span className={`text-xs transition-transform duration-150 ease-out ${open ? "-rotate-90" : ""}`}>‹</span>
        </span>
      </button>
      {open && (
        <div className="mr-4 mt-1 space-y-1 border-r border-slate-800 pr-2">
          {item.children.map((c) => (
            <NavLink key={c.label + c.to} to={c.to} className={leafClass}>
              <span className="text-xs opacity-60">•</span>
              <span>{c.label}</span>
              <Badge n={c.badgeKey ? badges[c.badgeKey] : 0} red={c.badgeRed} />
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

function CommandPalette({ open, onClose }) {
  const [q, setQ] = React.useState("");
  const navigate = useNavigate();
  const inputRef = React.useRef(null);
  React.useEffect(() => { if (open) { setQ(""); setTimeout(() => inputRef.current?.focus(), 30); } }, [open]);
  if (!open) return null;
  const query = q.trim().toLowerCase();
  const results = query
    ? PAGES.filter((p) => (p.label + " " + p.syn).toLowerCase().includes(query))
    : PAGES;
  const go = (to) => { navigate(to); onClose(); };
  return (
    <div className="fixed inset-0 z-[60] bg-black/60 flex items-start justify-center pt-24 px-4" onClick={onClose}>
      <div className="w-full max-w-lg bg-slate-900 border border-slate-700 rounded-xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <input ref={inputRef} className="w-full bg-slate-900 px-4 py-3 text-sm outline-none border-b border-slate-800"
          placeholder="جستجوی صفحه… (Enter برای رفتن، Esc برای بستن)"
          value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "Enter" && results[0]) go(results[0].to);
          }} />
        <div className="max-h-80 overflow-y-auto">
          {results.length === 0 ? (
            <p className="p-4 text-sm text-slate-500">موردی یافت نشد.</p>
          ) : results.map((p) => (
            <button key={p.label + p.to} onClick={() => go(p.to)}
              className="w-full text-right px-4 py-2 text-sm hover:bg-slate-800 flex items-center justify-between">
              <span>{p.label}</span>
              <span className="text-xs text-slate-600 font-mono">{p.to}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Layout() {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(() => localStorage.getItem(LS_COLLAPSED) === "1");
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [badges, setBadges] = React.useState({ incidents: 0, inbox: 0, queue: 0 });
  const [lastSync, setLastSync] = React.useState(null);

  const toggleCollapse = () => setCollapsed((c) => { localStorage.setItem(LS_COLLAPSED, c ? "0" : "1"); return !c; });

  // Actionable badges only (inbox unread / incidents / queue). Never vanity counts.
  React.useEffect(() => {
    const load = async () => {
      const [inc, stats, q] = await Promise.all([
        IncidentsApi.list(true).catch(() => []),
        InboxApi.stats().catch(() => ({})),
        QueueApi.summary().catch(() => ({})),
      ]);
      setBadges({ incidents: (inc || []).length, inbox: stats?.unread || 0, queue: q?.total || 0 });
      setLastSync(Date.now());
    };
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  // ⌘K / Ctrl+K command palette.
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); setPaletteOpen((o) => !o); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const syncAgo = lastSync ? Math.max(0, Math.round((Date.now() - lastSync) / 60000)) : null;

  return (
    <div className="flex h-full relative">
      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-30 h-14 bg-[#0F1214] border-b border-slate-800 flex items-center justify-between px-4">
        <h1 className="text-base font-bold text-brand">افراکالا</h1>
        <div className="flex items-center gap-3">
          <button aria-label="جستجو" onClick={() => setPaletteOpen(true)} className="text-xl text-slate-300">⌕</button>
          <button aria-label="منو" onClick={() => setMobileOpen(true)} className="text-2xl text-slate-300 leading-none">☰</button>
        </div>
      </div>

      {mobileOpen && <div className="md:hidden fixed inset-0 z-40 bg-black/60" onClick={() => setMobileOpen(false)} />}

      {/* Sidebar (RTL → right side) */}
      <aside
        className={`${collapsed ? "w-16" : "w-60"} shrink-0 bg-[#0F1214] border-l border-slate-800 flex flex-col
          fixed inset-y-0 right-0 z-50 transform transition-[transform,width] duration-200 ease-out md:static md:z-auto md:translate-x-0
          ${mobileOpen ? "translate-x-0" : "translate-x-full md:translate-x-0"}`}
        onClick={(e) => { if (e.target.closest("a")) setMobileOpen(false); }}
      >
        <div className="p-4 border-b border-slate-800 flex items-center justify-between gap-2">
          {!collapsed && (
            <div className="min-w-0">
              <h1 className="text-lg font-bold text-brand">افراکالا</h1>
              <p className="text-xs text-slate-500 mt-0.5 truncate">پیام‌رسان افراکالا</p>
            </div>
          )}
          <div className="flex items-center gap-1">
            {!collapsed && <button aria-label="جستجو (Ctrl+K)" title="جستجو (Ctrl+K)" onClick={() => setPaletteOpen(true)} className="text-slate-400 hover:text-white text-lg w-9 h-9 rounded-lg hover:bg-slate-800">⌕</button>}
            <button aria-label={collapsed ? "باز کردن منو" : "جمع کردن منو"} title={collapsed ? "باز کردن" : "جمع کردن"} onClick={toggleCollapse} className="hidden md:flex text-slate-400 hover:text-white text-lg w-9 h-9 rounded-lg hover:bg-slate-800 items-center justify-center">{collapsed ? "»" : "«"}</button>
            <button className="md:hidden text-slate-400 text-xl leading-none" aria-label="بستن" onClick={() => setMobileOpen(false)}>×</button>
          </div>
        </div>

        <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
          {NAV.map((n, i) =>
            n.separator ? (
              <div key={`sep${i}`} className="my-2 border-t border-slate-800" />
            ) : n.children ? (
              <NavGroup key={n.label} item={n} badges={badges} collapsed={collapsed} />
            ) : (
              <NavLink key={n.to} to={n.to} end={n.end} title={n.label} className={leafClass}>
                <span className="text-base">{n.icon}</span>
                {!collapsed && <span className="font-medium">{n.label}</span>}
              </NavLink>
            )
          )}
        </nav>

        {!collapsed && (
          <div className="p-3 text-xs text-slate-500 border-t border-slate-800 space-y-0.5">
            <div className="flex items-center gap-1">متصل به سرور <span className="text-emerald-400">🟢</span></div>
            <div>آخرین همگام‌سازی: {syncAgo == null ? "…" : syncAgo === 0 ? "چند لحظه پیش" : `${fa(syncAgo)} دقیقه پیش`}</div>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto pb-16 md:pb-0">
        <div className="max-w-6xl mx-auto p-6 pt-20 md:pt-6">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom bar — the 4 most-used */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 h-14 bg-[#0F1214] border-t border-slate-800 flex">
        {MOBILE_BAR.map((m) => (
          <NavLink key={m.to} to={m.to} end={m.end}
            className={({ isActive }) => `flex-1 flex flex-col items-center justify-center gap-0.5 text-xs ${isActive ? "text-brand font-bold" : "text-slate-400"}`}>
            <span className="text-lg">{m.icon}</span>
            <span>{m.label}</span>
          </NavLink>
        ))}
      </nav>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
