import React from "react";
import { Link } from "react-router-dom";
import { ObservationApi } from "../api.js";
import {
  faNum,
  mapOwnerReport,
  reasonLabel,
  shiftDateUtc,
  todayUtc,
  STATUS_COLOR,
  EVIDENCE_CLASS_FA,
} from "../observation/ownerViewModel.js";

const SHELL = {
  green: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100",
  red: "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950/40 dark:text-red-100",
  orange: "border-orange-300 bg-orange-50 text-orange-900 dark:border-orange-700 dark:bg-orange-950/40 dark:text-orange-100",
  gray: "border-slate-300 bg-slate-50 text-slate-800 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-100",
};

const TIMELINE_TONE = {
  WAITING: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  IN_PROGRESS: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-100",
  VALID: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
  INVALID: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-100",
  REVIEW: "bg-orange-100 text-orange-900 dark:bg-orange-950 dark:text-orange-100",
  INSUFFICIENT: "bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-100",
  NOT_APPLICABLE: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

function Card({ title, value, hint }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3 sm:p-4">
      <p className="text-xs text-muted mb-1">{title}</p>
      <p className="text-lg sm:text-xl font-bold tabular-nums" dir="ltr">{value}</p>
      {hint ? <p className="text-[11px] opacity-70 mt-1 leading-relaxed">{hint}</p> : null}
    </div>
  );
}

function Section({ title, children, testid }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-4 sm:p-5 space-y-3" data-testid={testid}>
      <h2 className="text-base sm:text-lg font-bold">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, value, ltr = false }) {
  return (
    <div className="flex justify-between gap-3 text-sm py-0.5">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-left" dir={ltr ? "ltr" : "rtl"}>{value}</span>
    </div>
  );
}

export default function DailyObservationReportPage() {
  const [date, setDate] = React.useState(() => todayUtc());
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [view, setView] = React.useState(null);
  const abortRef = React.useRef(null);

  const load = React.useCallback(async (day) => {
    if (abortRef.current) abortRef.current.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setError(null);
    try {
      const data = await ObservationApi.report(day, { includeTimeline: true, signal: ac.signal });
      if (ac.signal.aborted) return;
      const mapped = mapOwnerReport(data);
      if (mapped.error) {
        setView(null);
        setError("گزارش روزانه در حال حاضر در دسترس نیست. هیچ نتیجه‌ای را PASS فرض نکنید.");
      } else {
        setView(mapped);
      }
    } catch (e) {
      if (ac.signal.aborted || e?.code === "ERR_CANCELED") return;
      setView(null);
      setError("گزارش روزانه در حال حاضر در دسترس نیست. هیچ نتیجه‌ای را PASS فرض نکنید.");
    } finally {
      if (!ac.signal.aborted) setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load(date);
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, [date, load]);

  React.useEffect(() => {
    const id = setInterval(() => {
      if (document.hidden) return;
      load(date);
    }, 60_000);
    return () => clearInterval(id);
  }, [date, load]);

  const r = view?.report;
  const color = STATUS_COLOR[r?.overall_status] || "gray";
  const shell = SHELL[color] || SHELL.gray;

  return (
    <div className="space-y-5" dir="rtl" data-testid="daily-observation-report-page">
      <header className="space-y-2">
        <h1 className="text-xl sm:text-2xl font-bold">گزارش روزانه دوره مشاهده</h1>
        <p className="text-sm text-muted leading-relaxed">
          بررسی روزانه نشست دوم Shadow بدون دخالت در اجرای واقعی
        </p>
        <p className="text-xs opacity-70">
          Phase 7 هنوز کامل پذیرفته نشده و Phase 8 همچنان مسدود است.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-secondary text-sm" onClick={() => setDate(shiftDateUtc(date, -1))}>
          روز قبل
        </button>
        <button type="button" className="btn-secondary text-sm" onClick={() => setDate(todayUtc())}>
          امروز
        </button>
        <button
          type="button"
          className="btn-secondary text-sm"
          onClick={() => {
            const n = shiftDateUtc(date, 1);
            if (n <= todayUtc()) setDate(n);
          }}
        >
          روز بعد
        </button>
        <label className="text-sm flex items-center gap-2">
          <span>انتخاب تاریخ</span>
          <input
            type="date"
            className="input text-sm"
            dir="ltr"
            value={date}
            max={todayUtc()}
            onChange={(e) => e.target.value && setDate(e.target.value)}
            aria-label="انتخاب تاریخ گزارش"
          />
        </label>
        <button type="button" className="btn-secondary text-sm" onClick={() => load(date)} data-testid="observation-refresh">
          به‌روزرسانی نمایش
        </button>
        <Link to="/" className="text-sm text-brand underline underline-offset-2">بازگشت به داشبورد</Link>
      </div>

      {loading && (
        <div className="card text-sm" role="status" aria-live="polite">
          در حال دریافت گزارش روزانه…
        </div>
      )}
      {error && !loading && (
        <div className="card border-amber-300 bg-amber-50 text-amber-900 text-sm" role="alert">
          {error}
        </div>
      )}

      {r && !loading && (
        <>
          <section className={`rounded-xl border p-4 sm:p-5 ${shell}`} aria-label="خلاصه وضعیت روز">
            <div className="flex flex-wrap justify-between gap-3">
              <div>
                <p className="text-sm opacity-80">تاریخ UTC: <span dir="ltr">{r.report_date_utc}</span></p>
                <p className="font-bold text-lg mt-1">{r.dayLabel}</p>
                <p className="text-sm mt-1">{r.session_label || "نشست دوم (Session 2)"}</p>
                <p className="text-xs mt-1 opacity-70" dir="ltr">contract: {r.report_version}</p>
              </div>
              <div className="text-left space-y-1" dir="rtl">
                <span className="inline-flex rounded-full border border-current/20 px-3 py-1 text-sm font-semibold">
                  {r.statusFa}
                </span>
                <p className="text-xs opacity-70">کد فنی: <span dir="ltr">{r.overall_status}</span></p>
                <p className="text-xs">قابل‌شمارش: {r.can_count_as_valid_day ? "بله" : "خیر"}</p>
              </div>
            </div>
          </section>

          <section
            className="rounded-xl border border-sky-300/50 bg-sky-50/80 dark:bg-sky-950/30 dark:border-sky-800 p-4"
            data-testid="owner-action-card"
          >
            <h2 className="font-bold text-base">امروز چه کاری باید انجام دهم؟</h2>
            <p className="mt-2 text-sm leading-relaxed font-medium">{r.ownerActionFa}</p>
            {(r.unknown_findings || []).length > 0 && (
              <p className="mt-2 text-xs opacity-80">
                برخی موارد قابل‌اثبات نیستند و به‌صورت نامشخص نمایش داده شده‌اند.
              </p>
            )}
          </section>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="summary-cards">
            <Card title="نتیجه امروز" value={r.statusFa} hint={`کد: ${r.overall_status}`} />
            <Card title="Snapshot مورد انتظار" value={faNum(r.expected_periodic_ticks)} />
            <Card title="Snapshot واقعی دوره‌ای" value={faNum(r.actual_periodic_snapshots)} />
            <Card title="تغییر نسبت به روز قبل" value={faNum(r.snapshot_delta_vs_previous_day)} />
            <Card title="حساب‌های مورد انتظار" value={faNum(r.accounts_expected)} />
            <Card title="حساب‌های پوشش‌داده‌شده" value={faNum(r.accounts_covered)} />
            <Card title="آخرین Snapshot" value={r.last_snapshot_at || "نامشخص"} hint="زمان UTC" />
            <Card title="RUNTIME_UNKNOWN" value={faNum(r.runtime_unknown_count)} />
            <Card title="live_state_missing" value={faNum(r.live_state_missing_count)} />
            <Card
              title="HIGH / CRITICAL"
              value={`${faNum(r.by_severity?.HIGH || 0)} / ${faNum(r.by_severity?.CRITICAL || 0)}`}
            />
            <Card title="Cutover روشن" value={faNum(r.cutover_true_count)} />
            <Card
              title="نقض ایمنی"
              value={faNum(
                (r.simulation_only_violations || 0) +
                  (r.mutates_runtime_violations || 0) +
                  (r.executes_violations || 0)
              )}
            />
          </div>

          <Section title="جدول زمانی ۱۴ روزه Session 2" testid="observation-timeline">
            <p className="text-xs text-muted">
              روز معتبر فقط بر اساس شواهد Backend مشخص می‌شود؛ گذشت تقویم به‌تنهایی کافی نیست. Session 1 نامعتبر و خارج از این شمارش است.
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mt-2">
              {(view.timeline || []).map((t) => (
                <button
                  type="button"
                  key={t.report_date_utc}
                  className={`rounded-lg border border-line p-2 text-right ${TIMELINE_TONE[t.ui_status] || TIMELINE_TONE.WAITING}`}
                  onClick={() => t.ui_status !== "WAITING" && setDate(t.report_date_utc)}
                  aria-label={`روز ${t.calendar_day_index} ${t.ui_status_fa}`}
                >
                  <p className="text-xs font-bold">روز {faNum(t.calendar_day_index)}</p>
                  <p className="text-[11px]" dir="ltr">{t.report_date_utc}</p>
                  <p className="text-xs mt-1">{t.ui_status_fa}</p>
                  <p className="text-[11px] opacity-80 mt-0.5">
                    Snapshot: {t.actual_periodic_snapshots == null ? "—" : faNum(t.actual_periodic_snapshots)}
                  </p>
                </button>
              ))}
            </div>
          </Section>

          <Section title="وضعیت ثبت Snapshotها" testid="snapshot-section">
            <p className="text-xs text-muted leading-relaxed">
              Snapshot یک ثبت زمان‌دار از وضعیت Shadow است و هیچ پیام یا تغییری در سیستم واقعی ایجاد نمی‌کند.
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              <Row label="مورد انتظار دوره‌ای" value={faNum(r.expected_periodic_ticks)} />
              <Row label="واقعی دوره‌ای" value={faNum(r.actual_periodic_snapshots)} />
              <Row label="دستی / غیردوره‌ای" value={faNum(r.manual_snapshots)} />
              <Row label="جمع امروز" value={faNum(r.total_snapshots)} />
              <Row label="جمع روز قبل" value={faNum(r.previous_day_total_snapshots)} />
              <Row label="اولین Snapshot" value={r.first_snapshot_at || "نامشخص"} ltr />
              <Row label="آخرین Snapshot" value={r.last_snapshot_at || "نامشخص"} ltr />
              <Row label="تعارض ایدمپوتنسی" value={faNum(r.idempotency_conflict_count)} />
            </div>
          </Section>

          <Section title="سلامت زیرساخت" testid="infra-section">
            <div className="grid sm:grid-cols-2 gap-2">
              <Row label="Database" value={r.infraFa.database} />
              <Row label="Redis" value={r.infraFa.redis} />
              <Row label="Celery Worker" value={r.infraFa.celery} />
              <Row label="Celery Beat" value={r.infraFa.beat} />
              <Row label="Scheduler" value={r.infraFa.scheduler} />
              <Row label="پرچم Runtime" value={r.infraFa.runtimeFlag} />
              <Row label="پرچم Scheduler" value={r.infraFa.schedulerFlag} />
              <Row label="آخرین tick دوره‌ای" value={r.last_periodic_tick_at || "نامشخص"} ltr />
            </div>
          </Section>

          <Section title="کنترل‌های ایمنی" testid="safety-section">
            <div className="grid sm:grid-cols-2 gap-2">
              <Row label="Cutover true" value={r.safetyFa.cutover} />
              <Row label="نقض simulation_only" value={r.safetyFa.sim} />
              <Row label="نقض mutates_runtime" value={r.safetyFa.mut} />
              <Row label="نقض executes" value={r.safetyFa.exec} />
              <Row label="شواهد Mutation عملیاتی" value={r.safetyFa.operational} />
              <Row label="شواهد مسیر ارسال" value={r.send_path_evidence_status || "نامشخص"} ltr />
              <Row label="شواهد Green API" value={r.green_api_send_evidence_status || "نامشخص"} ltr />
              <Row label="شواهد Campaign" value={r.campaign_execution_evidence_status || "نامشخص"} ltr />
              <Row label="شواهد Journey" value={r.journey_mutation_evidence_status || "نامشخص"} ltr />
              <Row label="شواهد FleetState" value={r.fleet_state_mutation_evidence_status || "نامشخص"} ltr />
              <Row label="شواهد send_gate" value={r.send_gate_integrity_evidence_status || "نامشخص"} ltr />
            </div>
          </Section>

          <Section title="اختلاف‌ها و شواهد" testid="mismatch-section">
            <div className="grid sm:grid-cols-2 gap-2">
              <Row label="RUNTIME_UNKNOWN" value={faNum(r.runtime_unknown_count)} />
              <Row label="live_state_missing" value={faNum(r.live_state_missing_count)} />
              <Row label="SENSOR_STALE" value={faNum(r.sensor_stale_count)} />
              <Row label="DANGEROUS_MISMATCH" value={faNum(r.dangerous_mismatch_count)} />
              <Row label="LEGACY_MORE_PERMISSIVE" value={faNum(r.legacy_more_permissive_count)} />
              <Row label="V67_MORE_PERMISSIVE" value={faNum(r.v67_more_permissive_count)} />
              <Row label="POLICY_VERSION_MISMATCH" value={faNum(r.policy_version_mismatch_count)} />
              <Row label="INSUFFICIENT_EVIDENCE" value={faNum(r.insufficient_evidence_count)} />
            </div>
            <div className="mt-3 space-y-1">
              <p className="text-xs font-semibold">Reason codeهای برتر</p>
              {(r.top_reason_codes || []).slice(0, 8).map((x) => (
                <p key={x.code} className="text-xs">
                  {reasonLabel(x.code)} — {faNum(x.count)}
                </p>
              ))}
              {!(r.top_reason_codes || []).length && <p className="text-xs text-muted">موردی نیست</p>}
            </div>
          </Section>

          <Section title="یافته‌ها" testid="findings-section">
            <div className="space-y-3 text-sm">
              <div>
                <p className="font-semibold mb-1">موارد مسدودکننده</p>
                {(r.blocking_findings || []).length
                  ? r.blocking_findings.map((f) => <p key={f}>• {reasonLabel(f)}</p>)
                  : <p className="text-muted text-xs">موردی نیست</p>}
              </div>
              <div>
                <p className="font-semibold mb-1">موارد نیازمند بررسی</p>
                {(r.review_findings || []).length
                  ? r.review_findings.map((f) => <p key={f}>• {reasonLabel(f)}</p>)
                  : <p className="text-muted text-xs">موردی نیست</p>}
              </div>
              <div>
                <p className="font-semibold mb-1">موارد نامشخص</p>
                {(r.unknown_findings || []).length
                  ? r.unknown_findings.map((f) => <p key={f}>• {reasonLabel(f)}</p>)
                  : <p className="text-muted text-xs">موردی نیست</p>}
              </div>
            </div>
          </Section>

          <Section title="شواهد Runtime" testid="runtime-evidence-section">
            <p className="text-xs text-muted leading-relaxed">
              فقط شواهد روز و منابع bounded نمایش داده می‌شود. نبود خطا به‌معنی نبود Mutation نیست.
              Static به‌تنهایی برای PASS کافی نیست.
            </p>
            <div className="grid sm:grid-cols-2 gap-2 mt-2">
              <Row label="همبستگی" value={r.evidenceBundle?.correlation_status || "نامشخص"} ltr />
              <Row
                label="پشتیبانی از PASS روزانه"
                value={r.evidenceBundle?.can_support_daily_pass ? "بله" : "خیر"}
              />
            </div>
            <ul className="mt-2 space-y-1 text-xs">
              {(r.evidenceBundle?.runtime_items || []).slice(0, 12).map((it, idx) => (
                <li key={`rt-${idx}`}>
                  • {it.invariant}: {EVIDENCE_CLASS_FA[it.evidence_class] || it.evidence_class}
                  {" — "}{it.status}
                </li>
              ))}
              {!(r.evidenceBundle?.runtime_items || []).length && (
                <li className="text-muted">شواهد Runtime در پاسخ موجود نیست</li>
              )}
            </ul>
            {(r.evidenceBundle?.partial_items || []).length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold mb-1">مشاهده جزئی (بدون نسبت به Shadow)</p>
                {(r.evidenceBundle.partial_items || []).slice(0, 8).map((it, idx) => (
                  <p key={`pr-${idx}`} className="text-xs">
                    • {it.invariant}: {it.status} — {(it.reason_codes || []).join(", ")}
                  </p>
                ))}
              </div>
            )}
            {(r.evidenceBundle?.missing_items || []).length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold mb-1">شواهد ناقص / غیرقابل‌مشاهده</p>
                {(r.evidenceBundle.missing_items || []).slice(0, 8).map((it, idx) => (
                  <p key={`ms-${idx}`} className="text-xs">
                    • {it.invariant}: {EVIDENCE_CLASS_FA[it.evidence_class] || it.evidence_class}
                  </p>
                ))}
              </div>
            )}
          </Section>

          <Section title="شواهد Static / Manifest" testid="static-evidence-section">
            <div className="grid sm:grid-cols-2 gap-2">
              <Row label="وضعیت Manifest" value={r.staticManifestStatus} ltr />
              <Row label="SHA مستقر" value={r.deployedGitSha ? r.deployedGitSha.slice(0, 12) : "نامشخص"} ltr />
              <Row
                label="نسخه Manifest"
                value={r.staticManifest?.static_proof_version || "نامشخص"}
                ltr
              />
              <Row
                label="نسخه Evidence"
                value={r.evidenceBundle?.evidence_version || "نامشخص"}
                ltr
              />
            </div>
            <p className="text-xs text-muted mt-2 leading-relaxed">
              تطابق SHA فقط معماری release را تأیید می‌کند و به‌تنهایی روز را PASS نمی‌کند.
            </p>
          </Section>

          <Section title="Stop Conditions" testid="stop-conditions-section">
            <p className="text-xs text-muted mb-2">
              نمایش فقط‌خواندنی است. هیچ توقف خودکاری از این صفحه انجام نمی‌شود.
            </p>
            <div className="space-y-2">
              {(r.stopConditions || []).map((sc) => (
                <div
                  key={sc.key}
                  className="rounded-lg border border-line p-2 text-sm"
                  data-testid={`stop-${sc.key}`}
                >
                  <div className="flex justify-between gap-2">
                    <span className="font-semibold">{sc.title_fa}</span>
                    <span dir="ltr" className="text-xs">{sc.state}</span>
                  </div>
                  <p className="text-xs opacity-80 mt-1" dir="ltr">{sc.reason}</p>
                  <p className="text-xs mt-1">منبع: <span dir="ltr">{sc.evidence_source}</span></p>
                  <p className="text-xs mt-1">شدت: <span dir="ltr">{sc.severity}</span></p>
                  <p className="text-xs mt-1 leading-relaxed">{sc.owner_action_fa}</p>
                </div>
              ))}
              {!(r.stopConditions || []).length && (
                <p className="text-xs text-muted">موردی ثبت نشده</p>
              )}
            </div>
          </Section>

          <Section title="گزارش خودکار روزانه" testid="automated-report-section">
            <div className="grid sm:grid-cols-2 gap-2">
              <Row
                label="زمان زمان‌بندی (UTC)"
                value={r.automatedReportMeta?.schedule_utc || "06:00"}
                ltr
              />
              <Row
                label="معادل تهران"
                value={r.automatedReportMeta?.schedule_tehran || "09:30"}
                ltr
              />
              <Row
                label="نام Task"
                value={r.automatedReportMeta?.task_name || "tasks.daily_observation_report"}
                ltr
              />
              <Row label="اعلان / پیام" value="خیر" />
            </div>
            <p className="text-xs text-muted mt-2 leading-relaxed">
              گزارش روز کامل‌شده قبلی UTC به‌صورت خودکار ساخته می‌شود. این صفحه فقط GET می‌کند و
              دکمه اجرا/ارسال ندارد.
            </p>
          </Section>
        </>
      )}
    </div>
  );
}
