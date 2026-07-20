// V35 PART 4 — pure helpers for the guided onboarding wizard «راه‌اندازی».
// The backend (onboarding_service.derive_state) is the source of truth for locked/unlocked and
// the next-unlock time; this module maps the derived `phase` to the Persian single-next-action
// copy the wizard shows, and formats a live countdown. Kept pure + unit-tested (onboarding.test.js).

export const GATE_A_HOURS = 24; // SIM insertion → WhatsApp activation
export const GATE_B_HOURS = 24; // WhatsApp activation → Green API login

// phase → the ONE next action shown at a time (never more than one expected action).
export const PHASE_CONTENT = {
  gate_a_wait: {
    step: 1,
    title: "مرحلهٔ ۱ — انتظار پس از واردکردن سیم‌کارت",
    body:
      "سیم‌کارت ثبت شد. در این مدت با این سیم‌کارت تماس بگیرید و پیامک رد و بدل کنید — " +
      "با شماره‌های واقعی، نه به‌صورت خودکار. هنوز واتساپ را روی این شماره فعال نکنید.",
    locked: true,
  },
  activate_whatsapp: {
    step: 2,
    title: "مرحلهٔ ۲ — فعال‌سازی واتساپ",
    body:
      "حالا می‌توانید اکانت واتساپ این شماره را روی همین گوشی بالا بیاورید و تنظیمات " +
      "(نام، عکس پروفایل و…) را کامل کنید. پس از انجام، دکمهٔ تأیید را بزنید.",
    locked: false,
    action: "واتساپ را فعال کردم",
  },
  gate_b_wait: {
    step: 3,
    title: "مرحلهٔ ۳ — انتظار پیش از اتصال به Green API",
    body:
      "در این ۲۴ ساعت، این شماره را طبیعی روی گوشی استفاده کنید — هنوز به Green API وصل نکنید.",
    locked: true,
  },
  connect_green_api: {
    step: 4,
    title: "مرحلهٔ ۴ — اتصال به Green API و همکاری تیمی",
    body:
      "حالا وارد Green API شوید، این شماره را با اسکن QR وصل کنید، سپس دکمهٔ «همکاری تیمی» را " +
      "برای این اکانت فعال کنید.",
    locked: false,
    action: "به Green API وصل شد",
  },
  done: {
    step: 4,
    title: "راه‌اندازی کامل شد ✓",
    body: "این شماره با موفقیت راه‌اندازی و به Green API متصل شد. می‌توانید همکاری تیمی را مدیریت کنید.",
    locked: false,
  },
};

export function phaseContent(phase) {
  return PHASE_CONTENT[phase] || PHASE_CONTENT.gate_a_wait;
}

// Convert Western digits in a string to Persian numerals (display only).
export function faDigits(s) {
  return s == null ? "" : String(s).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
}

// Human countdown between now and an ISO unlock time. Returns "" when unlocked/absent.
// nowMs lets tests inject a deterministic clock.
export function formatCountdown(nextUnlockIso, nowMs) {
  if (!nextUnlockIso) return "";
  const target = Date.parse(nextUnlockIso);
  if (Number.isNaN(target)) return "";
  const now = nowMs == null ? Date.now() : nowMs;
  let diff = Math.floor((target - now) / 1000);
  if (diff <= 0) return "";
  const h = Math.floor(diff / 3600);
  diff -= h * 3600;
  const m = Math.floor(diff / 60);
  const parts = [];
  if (h > 0) parts.push(`${faDigits(h)} ساعت`);
  parts.push(`${faDigits(m)} دقیقه`);
  return parts.join(" و ");
}

// Progress order used to render the 4-step tracker.
export const STEP_ORDER = [1, 2, 3, 4];
