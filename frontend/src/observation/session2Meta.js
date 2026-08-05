/**
 * V67.1 — Session 2 observation reminder metadata (frontend-only).
 * Source of start/run_id: ops docs 107 (not a new backend API).
 * Day index = full UTC days elapsed since official CELERY start (Day 0 until 24h elapses).
 * This is calendar progress only — not proof of valid observation days.
 */

export const SESSION_2_META = Object.freeze({
  sessionLabelFa: "نشست دوم",
  sessionLabelEn: "Session 2",
  startedAtUtc: "2026-08-05T19:13:46.331651Z",
  runId: "9197e53f-4a25-404f-92b8-ad8a8d5e6acf",
  targetDays: 14,
  simulationOnly: true,
});

export const CALENDAR_DAY_DISCLAIMER =
  "این شمارنده فقط زمان تقویمی را نشان می‌دهد. معتبر بودن روزها فقط با گزارش‌های روزانه و ممیزی نهایی مشخص می‌شود.";

export const PURPOSE_TITLE = "این دوره برای چیست؟";
export const PURPOSE_BODY =
  "سیستم جدید در کنار سیستم اصلی کار می‌کند و فقط تصمیم‌ها و وضعیت‌ها را مشاهده و ثبت می‌کند. در این دوره هیچ ارسال واقعی، تغییر خودکار وضعیت، Canary یا Cutover توسط این کارت انجام نمی‌شود.";

export const DAILY_ACTION_TITLE = "آیا امروز کاری باید انجام دهم؟";
export const DAILY_ACTION_NORMAL =
  "اگر هشدار قرمز یا نارنجی نمی‌بینید، لازم نیست کاری انجام دهید. فقط روزی یک‌بار این کارت را بررسی کنید.";

export const DAILY_CHECKLIST = Object.freeze([
  "تعداد Snapshotها نسبت به روز قبل بیشتر شده باشد",
  "وضعیت زمان‌بند و اجرای سایه در حالت سالم باشد؛ اگر نامشخص است، گزارش روزانه بررسی شود",
  "خطای بحرانی جدید ثبت نشده باشد",
  "وضعیت Cutover همچنان خاموش باشد",
  "هشدار توقف یا نیاز به شروع مجدد نمایش داده نشده باشد",
  "گزارش روزانه ساعت ۰۹:۳۰ تهران بررسی شده باشد",
]);

export const ESCALATE_TITLE = "چه زمانی باید فوراً پیگیری کنم؟";
export const ESCALATE_ITEMS = Object.freeze([
  "روز شمار متوقف شد یا به عقب برگشت",
  "Snapshot جدید ثبت نشد",
  "وضعیت زمان‌بند، Redis، Celery یا پایگاه داده ناسالم شد",
  "هشدار بحرانی یا توقف اضطراری نمایش داده شد",
  "Cutover روشن شد",
  "اطلاعات کارت برای مدت طولانی نامشخص ماند",
  "عبارت نیاز به شروع مجدد نمایش داده شد",
  "Observation Session نامعتبر اعلام شد",
]);
export const ESCALATE_FOOTER =
  "در این حالت Phase 8 نباید شروع شود و ابتدا باید گزارش فنی بررسی شود.";

export const OWNER_DAILY_DUTY =
  "کار روزانه مالک: روزی یک‌بار، حدود ساعت ۰۹:۳۰ تهران، این کارت و گزارش روزانه Shadow را بررسی کنید.";
export const OWNER_NO_CHANGE =
  "اگر همه چیز عادی است، هیچ دکمه‌ای نزنید و هیچ تنظیمی را تغییر ندهید.";
export const OWNER_ESCALATE_HINT =
  "اگر هشدار بحرانی، قطع Snapshot یا وضعیت نامعتبر دیدید، گزارش را برای بررسی فنی ارسال کنید.";

export const SNAPSHOT_HINT = "Snapshot یعنی یک ثبت زمان‌دار از وضعیت سیستم در حالت مشاهده.";

/** @typedef {"WAITING"|"RUNNING"|"COMPLETED"|"INVALID"|"RESTART_REQUIRED"} ObservationStatus */

export const STATUS_COLORS = Object.freeze({
  WAITING: "gray",
  RUNNING: "blue",
  COMPLETED: "green",
  INVALID: "red",
  RESTART_REQUIRED: "orange",
});

export const STATUS_LABELS_FA = Object.freeze({
  WAITING: "در انتظار شروع",
  RUNNING: "در حال مشاهده",
  COMPLETED: "آماده ممیزی نهایی",
  INVALID: "نامعتبر",
  RESTART_REQUIRED: "نیازمند شروع مجدد",
});

export function faNum(n) {
  if (n == null || Number.isNaN(Number(n))) return "نامشخص";
  return Number(n).toLocaleString("fa-IR");
}

/**
 * @param {string|null|undefined} startedAtUtc ISO timestamp
 * @param {Date|number|string} [now]
 * @returns {boolean}
 */
export function isBeforeObservationStart(startedAtUtc, now = Date.now()) {
  if (!startedAtUtc) return false;
  const startMs = Date.parse(startedAtUtc);
  if (Number.isNaN(startMs)) return false;
  const nowMs = typeof now === "number" ? now : Date.parse(now);
  if (Number.isNaN(nowMs)) return false;
  return nowMs < startMs;
}

/**
 * @param {string|null|undefined} startedAtUtc ISO timestamp
 * @param {Date|number|string} [now]
 * @returns {number|null} day index (0..) or null if unknown / before start
 */
export function computeObservationDay(startedAtUtc, now = Date.now()) {
  if (!startedAtUtc) return null;
  const startMs = Date.parse(startedAtUtc);
  if (Number.isNaN(startMs)) return null;
  const nowMs = typeof now === "number" ? now : Date.parse(now);
  if (Number.isNaN(nowMs)) return null;
  if (nowMs < startMs) return null;
  return Math.floor((nowMs - startMs) / 86_400_000);
}

/**
 * @param {{ day: number|null, sessionActive?: boolean, invalid?: boolean, restartRequired?: boolean, beforeStart?: boolean }} p
 * @returns {ObservationStatus}
 */
export function resolveObservationStatus({
  day,
  sessionActive = true,
  invalid = false,
  restartRequired = false,
  beforeStart = false,
}) {
  if (restartRequired) return "RESTART_REQUIRED";
  if (invalid) return "INVALID";
  if (beforeStart || !sessionActive || day == null) return "WAITING";
  if (day >= 14) return "COMPLETED";
  return "RUNNING";
}

/**
 * @param {ObservationStatus} status
 * @returns {"gray"|"blue"|"green"|"red"|"orange"}
 */
export function statusColor(status) {
  return STATUS_COLORS[status] || "gray";
}

/**
 * @param {ObservationStatus} status
 * @returns {string}
 */
export function statusLabelFa(status) {
  return STATUS_LABELS_FA[status] || "نامشخص";
}

/**
 * @param {number|null} day
 * @param {{ beforeStart?: boolean }} [opts]
 * @returns {string}
 */
export function dayLabel(day, { beforeStart = false } = {}) {
  if (beforeStart) return "دوره مشاهده هنوز شروع نشده است";
  if (day == null || Number.isNaN(day)) return "روز فعلی نامشخص است";
  return `روز ${faNum(day)} از ۱۴`;
}

/**
 * Short progress line under the day counter.
 * @param {number|null} day
 * @param {{ beforeStart?: boolean }} [opts]
 */
export function progressHeadline(day, { beforeStart = false } = {}) {
  if (beforeStart) return "دوره مشاهده هنوز شروع نشده است";
  if (day == null || Number.isNaN(day)) return "روز فعلی نامشخص است";
  if (day < 14) return "مشاهده در حال انجام است";
  return "از نظر تقویمی آماده ممیزی نهایی است";
}

/**
 * Remaining calendar days until day index 14.
 * @param {number|null} day
 * @param {{ beforeStart?: boolean }} [opts]
 */
export function remainingLabel(day, { beforeStart = false } = {}) {
  if (beforeStart) return "شروع رسمی هنوز فرا نرسیده است";
  if (day == null || Number.isNaN(day)) return "مدت باقی‌مانده نامشخص است";
  if (day >= 14) return "۱۴ روز تقویمی سپری شده است";
  const left = 14 - day;
  return `حدود ${faNum(left)} روز تقویمی تا پایان شمارش ۱۴ روزه باقی مانده است`;
}

/**
 * Warning copy — never claims premature full Phase 7 acceptance.
 * @param {number|null} day
 * @param {{ beforeStart?: boolean }} [opts]
 * @returns {string}
 */
export function observationWarning(day, { beforeStart = false } = {}) {
  if (beforeStart) {
    return "دوره مشاهده هنوز شروع نشده است. تا پایان ۱۴ روز معتبر و ممیزی نهایی، Phase 8 نباید شروع شود.";
  }
  if (day == null || Number.isNaN(day)) {
    return "روز مشاهده نامشخص است. تا پایان ۱۴ روز معتبر و ممیزی نهایی، Phase 8 نباید شروع شود.";
  }
  if (day < 14) {
    return "این دوره هنوز ادامه دارد. تا پایان ۱۴ روز معتبر و ممیزی نهایی، Phase 8 نباید شروع شود.";
  }
  return "۱۴ روز تقویمی سپری شده است؛ اما تکمیل Phase 7 فقط پس از ممیزی نهایی و تأیید اعتبار همه روزها مجاز است.";
}

/**
 * @param {string} isoUtc
 * @returns {string}
 */
export function formatTehranFromUtc(isoUtc) {
  if (!isoUtc) return "نامشخص";
  const d = new Date(isoUtc);
  if (Number.isNaN(d.getTime())) return "نامشخص";
  try {
    return (
      new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Tehran",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(d) + " زمان تهران"
    );
  } catch {
    return "نامشخص";
  }
}

/**
 * Parse GET /fleet/accounts payload. Fail closed on malformed data.
 * @param {unknown} data
 * @returns {{ fleetAccountCount: number|null, anyCutover: boolean|null }}
 */
export function parseFleetAccountsHint(data) {
  if (!Array.isArray(data)) {
    return { fleetAccountCount: null, anyCutover: null };
  }
  return {
    fleetAccountCount: data.length,
    anyCutover: data.some((a) => a && a.cutover === true),
  };
}

function liveSchedulerRuntimeShadow(v) {
  if (v === true) return "روشن";
  if (v === false) return "خاموش";
  return "نامشخص";
}

function liveCutover(v) {
  if (v === true) return "روشن — هشدار";
  if (v === false) return "خاموش";
  return "نامشخص";
}

function liveCanaryOrHuman(v) {
  if (v === true) return "فعال — نیازمند بررسی";
  if (v === false) return "شروع نشده";
  return "نامشخص";
}

/**
 * Build card view-model (pure; no network).
 * @param {object} opts
 */
export function buildObservationCardModel(opts = {}) {
  const {
    startedAtUtc = SESSION_2_META.startedAtUtc,
    runId = SESSION_2_META.runId,
    now = Date.now(),
    sessionActive = true,
    invalid = false,
    restartRequired = false,
    fleetAccountCount = null,
    snapshotCount = null,
    scheduler = null,
    runtime = null,
    shadow = null,
    cutover = null,
    canary = false,
    humanContacts = false,
  } = opts;

  const beforeStart = isBeforeObservationStart(startedAtUtc, now);
  const day = computeObservationDay(startedAtUtc, now);
  const status = resolveObservationStatus({
    day,
    sessionActive,
    invalid,
    restartRequired,
    beforeStart,
  });

  return {
    title: "دوره مشاهده ۱۴ روزه",
    subtitle: "نشست دوم — اجرای سایه فقط برای مشاهده",
    sessionBadge: "نشست دوم (Session 2)",
    simulationBadge: "فقط شبیه‌سازی و مشاهده",
    day,
    beforeStart,
    dayLabel: dayLabel(day, { beforeStart }),
    progressHeadline: progressHeadline(day, { beforeStart }),
    remainingLabel: remainingLabel(day, { beforeStart }),
    status,
    statusLabel: statusLabelFa(status),
    statusColor: statusColor(status),
    warning: observationWarning(day, { beforeStart }),
    disclaimer: CALENDAR_DAY_DISCLAIMER,
    purposeTitle: PURPOSE_TITLE,
    purposeBody: PURPOSE_BODY,
    dailyActionTitle: DAILY_ACTION_TITLE,
    dailyActionNormal: DAILY_ACTION_NORMAL,
    dailyChecklist: DAILY_CHECKLIST,
    escalateTitle: ESCALATE_TITLE,
    escalateItems: ESCALATE_ITEMS,
    escalateFooter: ESCALATE_FOOTER,
    ownerDailyDuty: OWNER_DAILY_DUTY,
    ownerNoChange: OWNER_NO_CHANGE,
    ownerEscalateHint: OWNER_ESCALATE_HINT,
    snapshotHint: SNAPSHOT_HINT,
    simulationOnly: true,
    currentSession: "نشست دوم (Session 2)",
    currentDay: day == null ? "نامشخص" : faNum(day),
    startedAtUtc: startedAtUtc || "نامشخص",
    startedAtTehran: formatTehranFromUtc(startedAtUtc),
    runId: runId || "نامشخص",
    fleetAccountCount: fleetAccountCount == null ? "نامشخص" : faNum(fleetAccountCount),
    fleetAccountCountLabel: "تعداد حساب‌های ناوگان",
    snapshotCount: snapshotCount == null ? "نامشخص" : faNum(snapshotCount),
    snapshotCountLabel: "تعداد Snapshotهای ثبت‌شده",
    labels: {
      currentSession: "نشست فعلی",
      currentDay: "روز فعلی",
      startedAtUtc: "شروع به وقت جهانی (UTC)",
      startedAtTehran: "شروع به وقت تهران",
      runId: "شناسه اجرا",
      liveTitle: "وضعیت‌های فنی — فقط نمایش",
      scheduler: "زمان‌بند",
      runtime: "اجرای سایه",
      shadow: "سامانه مشاهده",
      cutover: "Cutover",
      canary: "Canary",
      humanContacts: "مخاطبان انسانی",
    },
    live: {
      scheduler: liveSchedulerRuntimeShadow(scheduler),
      runtime: liveSchedulerRuntimeShadow(runtime),
      shadow: liveSchedulerRuntimeShadow(shadow),
      cutover: liveCutover(cutover),
      canary: liveCanaryOrHuman(canary),
      humanContacts: liveCanaryOrHuman(humanContacts),
    },
    actions: [],
  };
}
