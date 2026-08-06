/**
 * Owner ViewModel — maps Phase A contract to Persian UI labels.
 * Does NOT recompute PASS/FAIL / expected ticks / validity.
 */

export const STATUS_FA = Object.freeze({
  PASS: "معتبر بر اساس شواهد موجود",
  FAIL: "نامعتبر",
  REVIEW_REQUIRED: "نیازمند بررسی فنی",
  INSUFFICIENT_EVIDENCE: "شواهد ناکافی",
  NOT_APPLICABLE: "قابل‌اعمال نیست",
});

export const STATUS_COLOR = Object.freeze({
  PASS: "green",
  FAIL: "red",
  REVIEW_REQUIRED: "orange",
  INSUFFICIENT_EVIDENCE: "gray",
  NOT_APPLICABLE: "gray",
});

export const INFRA_FA = Object.freeze({
  HEALTHY: "سالم",
  UNHEALTHY: "ناسالم",
  DEGRADED: "دارای اختلال",
  UNKNOWN: "نامشخص",
  NOT_APPLICABLE: "قابل‌اعمال نیست",
  INSUFFICIENT_EVIDENCE: "شواهد ناکافی",
});

export const REASON_FA = Object.freeze({
  live_state_missing: "وضعیت زنده در دسترس نیست",
  runtime_unknown: "وضعیت زمان اجرا نامشخص",
  RUNTIME_UNKNOWN: "وضعیت زمان اجرا نامشخص",
  HIGH_CRITICAL_PRESENT: "اختلاف با شدت بالا یا بحرانی",
  MUTATION_EVIDENCE_INSUFFICIENT: "شواهد Mutation عملیاتی ناکافی است",
  RUNTIME_MUTATION_NOT_OBSERVABLE: "Mutation نسبت‌داده‌شده به Shadow قابل‌مشاهده نیست",
  STATIC_MANIFEST_INCOMPLETE: "Static Manifest ناقص یا نامشخص است",
  STATIC_MANIFEST_MISMATCH: "عدم تطابق SHA مستقر با Manifest",
  EVIDENCE_BUNDLE_MISSING: "بسته شواهد موجود نیست",
  TICK_GAP_UNRATIFIED: "کمبود Snapshot دوره‌ای (آستانه تأیید نشده)",
  CUTOVER_TRUE: "Cutover روشن است",
  NO_COHORT: "cohort ناوگان خالی است",
  DATABASE_UNKNOWN: "وضعیت پایگاه داده نامشخص",
  REDIS_UNKNOWN: "وضعیت Redis نامشخص",
  CELERY_WORKER_UNKNOWN: "وضعیت Celery نامشخص",
  BEAT_UNKNOWN: "وضعیت Celery Beat نامشخص",
  SCHEDULER_UNKNOWN: "وضعیت زمان‌بند نامشخص",
});

export const EVIDENCE_CLASS_FA = Object.freeze({
  RUNTIME_VERIFIED: "تأییدشده در Runtime",
  STATIC_VERIFIED: "تأییدشده Static",
  PARTIALLY_OBSERVED: "مشاهده جزئی",
  NOT_OBSERVABLE: "غیرقابل‌مشاهده",
});

export function faNum(n) {
  if (n == null || n === "" || Number.isNaN(Number(n))) return "نامشخص";
  return Number(n).toLocaleString("fa-IR");
}

export function displayVal(v) {
  if (v == null || v === "") return "نامشخص";
  return v;
}

export function reasonLabel(code) {
  if (!code) return "نامشخص";
  const fa = REASON_FA[code];
  return fa ? `${fa} (${code})` : String(code);
}

export function mapOwnerReport(payload) {
  if (!payload || typeof payload !== "object" || !payload.report) {
    return { error: "malformed", report: null, timeline: [] };
  }
  const r = payload.report;
  if (r.phase7_fully_accepted === true || r.phase8_allowed === true) {
    // Refuse to display unsafe claims — treat as malformed for validity UI.
    return { error: "unsafe_flags", report: null, timeline: [] };
  }
  const status = r.overall_status || "INSUFFICIENT_EVIDENCE";
  return {
    error: null,
    delivery: payload.delivery || null,
    report: {
      ...r,
      statusFa: STATUS_FA[status] || status,
      statusColor: STATUS_COLOR[status] || "gray",
      dayLabel:
        r.calendar_day_index == null
          ? "روز تقویمی نامشخص"
          : `روز ${faNum(r.calendar_day_index)} از ${faNum(r.expected_total_days ?? 14)}`,
      ownerActionFa: r.owner_action_fa || STATUS_FA.INSUFFICIENT_EVIDENCE,
      infraFa: {
        database: INFRA_FA[r.database_status] || "نامشخص",
        redis: INFRA_FA[r.redis_status] || "نامشخص",
        celery: INFRA_FA[r.celery_worker_status] || "نامشخص",
        beat: INFRA_FA[r.celery_beat_status] || "نامشخص",
        scheduler: INFRA_FA[r.scheduler_status] || "نامشخص",
        runtimeFlag: INFRA_FA[r.shadow_runtime_flag_status] || "نامشخص",
        schedulerFlag: INFRA_FA[r.shadow_scheduler_flag_status] || "نامشخص",
      },
      safetyFa: {
        cutover: faNum(r.cutover_true_count),
        sim: faNum(r.simulation_only_violations),
        mut: faNum(r.mutates_runtime_violations),
        exec: faNum(r.executes_violations),
        operational: INFRA_FA[r.operational_mutation_evidence_status] || "نامشخص",
      },
      evidenceBundle: r.evidence_bundle && typeof r.evidence_bundle === "object" ? r.evidence_bundle : null,
      staticManifest: r.static_manifest && typeof r.static_manifest === "object" ? r.static_manifest : null,
      staticManifestStatus: r.static_manifest_status || "UNKNOWN",
      deployedGitSha: r.deployed_git_sha || null,
      stopConditions: Array.isArray(r.stop_conditions) ? r.stop_conditions : [],
      automatedReportMeta: r.automated_report_meta && typeof r.automated_report_meta === "object"
        ? r.automated_report_meta
        : null,
    },
    timeline: Array.isArray(payload.timeline) ? payload.timeline : [],
  };
}

export function shiftDateUtc(isoDay, deltaDays) {
  const [y, m, d] = isoDay.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + deltaDays);
  return dt.toISOString().slice(0, 10);
}

export function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}
