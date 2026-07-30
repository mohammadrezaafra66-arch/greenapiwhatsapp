import React from "react";

// V15 Item 25 — a small ❓ that reveals a Persian explanation on hover/focus.
// Dark background, light text, RTL, max-width 250px. Keyboard-accessible.
export default function HelpTip({ text }) {
  return (
    <span className="relative inline-flex group align-middle mr-1">
      <button
        type="button"
        tabIndex={0}
        aria-label={text}
        className="w-4 h-4 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 text-[10px] leading-4 text-center cursor-help"
      >
        ؟
      </button>
      <span
        dir="rtl"
        className="pointer-events-none absolute z-[70] hidden group-hover:block group-focus-within:block
                   bottom-full right-0 mb-1 w-[250px] rounded-lg bg-surface border border-line
                   text-ink text-xs p-2 leading-relaxed shadow-card"
      >
        {text}
      </span>
    </span>
  );
}

// Shared tooltip copy (Item 25 table).
export const TIPS = {
  idInstance: "شناسه عددی instance در سرویس — خودکار پر می‌شود. دست نزنید.",
  phone: "شماره تلفنی که با QR یا کد وصل شده — خودکار پر می‌شود.",
  token: "رمز اتصال به سرویس — مخفی و محرمانه. هرگز به کسی ندهید.",
  name: "نام دلخواه برای شناسایی در سامانه — اختیاری. می‌توانید تغییر دهید.",
  tariff: "نوع اشتراک سرویس (Partner/Business) — خودکار از سرویس خوانده می‌شود.",
  daysActive: "تعداد روزهایی که این شماره متصل و فعال بوده — مهم برای دوره گرم‌سازی (warm-up).",
  health: "امتیاز ۰ تا ۱۰۰ بر اساس ظرفیت باقی‌مانده و نرخ کارت زرد ۷ روز اخیر.",
};
