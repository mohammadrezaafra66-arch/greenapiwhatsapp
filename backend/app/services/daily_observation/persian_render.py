"""Persian owner-facing text renderer for DailyObservationReport."""
from __future__ import annotations
from app.services.daily_observation.contract import DailyObservationReport


def _fa_bool_count(n: int) -> str:
    return str(n)


def render_persian_text(report: DailyObservationReport, *, show_evidence: bool = False) -> str:
    day = report.calendar_day_index
    day_txt = f"روز تقویمی {day} از {report.expected_total_days}" if day is not None else "روز تقویمی نامشخص"
    delta = report.snapshot_delta_vs_previous_day
    if delta is None:
        delta_txt = "نامشخص"
    elif delta > 0:
        delta_txt = f"رشد نسبت به روز قبل: +{delta}"
    elif delta == 0:
        delta_txt = "بدون تغییر نسبت به روز قبل"
    else:
        delta_txt = f"کاهش نسبت به روز قبل: {delta}"

    lines = [
        "گزارش روزانه دوره مشاهده Phase 7",
        "=" * 40,
        f"تاریخ UTC: {report.report_date_utc}",
        f"معادل تقریبی تولید گزارش (تهران): {report.generated_at_tehran}",
        f"نشست: {report.session_label}",
        day_txt,
        f"نسخه قرارداد: {report.report_version}",
        "",
        f"نتیجه کلی: {report.overall_status}",
        f"آیا این روز قابل‌شمارش است؟ {'بله' if report.can_count_as_valid_day else 'خیر'}",
        f"آیا نیاز به بررسی فنی دارد؟ {'بله' if report.requires_human_review else 'خیر'}",
        f"Phase 7 کامل پذیرفته شده؟ خیر (همیشه false در Phase A)",
        f"Phase 8 مجاز است؟ خیر (همیشه false در Phase A)",
        "",
        "— Snapshot —",
        f"تعداد Snapshot مورد انتظار (دوره‌ای): {report.expected_periodic_ticks if report.expected_periodic_ticks is not None else 'نامشخص'}",
        f"تعداد Snapshot واقعی دوره‌ای (CELERY_PERIODIC): {report.actual_periodic_snapshots}",
        f"تعداد Snapshot دستی/غیردوره‌ای: {report.manual_snapshots}",
        f"جمع Snapshot امروز: {report.total_snapshots}",
        f"جمع Snapshot روز قبل: {report.previous_day_total_snapshots if report.previous_day_total_snapshots is not None else 'نامشخص'}",
        delta_txt,
        f"اولین Snapshot: {report.first_snapshot_at or 'نامشخص'}",
        f"آخرین Snapshot: {report.last_snapshot_at or 'نامشخص'}",
        f"حساب‌های مورد انتظار (cohort با cutover=false): {report.accounts_expected}",
        f"حساب‌های پوشش‌داده‌شده: {report.accounts_covered}",
        "",
        "— زیرساخت —",
        f"وضعیت Database: {report.database_status}",
        f"وضعیت Redis: {report.redis_status}",
        f"وضعیت Celery Worker: {report.celery_worker_status}",
        f"وضعیت Celery Beat: {report.celery_beat_status}",
        f"وضعیت Scheduler: {report.scheduler_status}",
        f"پرچم Runtime: {report.shadow_runtime_flag_status}",
        f"پرچم Scheduler: {report.shadow_scheduler_flag_status}",
        "",
        "— ایمنی —",
        f"وضعیت Cutover (تعداد cutover=true): {_fa_bool_count(report.cutover_true_count)}",
        f"نقض simulation_only: {report.simulation_only_violations}",
        f"نقض mutates_runtime: {report.mutates_runtime_violations}",
        f"نقض executes: {report.executes_violations}",
        f"شواهد Mutation عملیاتی: {report.operational_mutation_evidence_status}",
        "",
        "— Mismatch —",
        f"RUNTIME_UNKNOWN: {report.runtime_unknown_count}",
        f"live_state_missing: {report.live_state_missing_count}",
        f"SENSOR_STALE: {report.sensor_stale_count}",
        f"HIGH: {report.by_severity.get('HIGH', 0)}",
        f"CRITICAL: {report.by_severity.get('CRITICAL', 0)}",
        "",
        "— موارد نامشخص / بررسی —",
    ]
    if report.unknown_findings:
        for u in report.unknown_findings:
            lines.append(f"• نامشخص: {u}")
    else:
        lines.append("• مورد نامشخص ثبت‌شده‌ای نیست")
    if report.review_findings:
        for r in report.review_findings:
            lines.append(f"• بررسی: {r}")
    if report.blocking_findings:
        for b in report.blocking_findings:
            lines.append(f"• مسدودکننده: {b}")

    lines += [
        "",
        "اقدام پیشنهادی مالک:",
        report.owner_action_fa or "نامشخص",
    ]

    if show_evidence:
        lines.append("")
        lines.append("— شواهد Runtime مشاهده‌شده —")
        lines.extend(f"• {x}" for x in (report.runtime_observed_evidence or ["هیچ"]))
        lines.append("— شواهد Static/Test —")
        lines.extend(f"• {x}" for x in (report.static_test_evidence or ["هیچ"]))
        lines.append(f"دلایل اعتبار: {', '.join(report.validity_reason_codes) or '—'}")

    lines.append("")
    lines.append("این خروجی فقط‌خواندنی است و هیچ تنظیمی را تغییر نمی‌دهد.")
    return "\n".join(lines) + "\n"


def render_text(report: DailyObservationReport) -> str:
    d = report.to_dict()
    keys = [
        "report_version", "report_date_utc", "session_id", "calendar_day_index",
        "overall_status", "can_count_as_valid_day", "expected_periodic_ticks",
        "actual_periodic_snapshots", "total_snapshots", "previous_day_total_snapshots",
        "snapshot_delta_vs_previous_day", "accounts_expected", "accounts_covered",
        "runtime_unknown_count", "live_state_missing_count", "cutover_true_count",
        "database_status", "redis_status", "celery_worker_status", "scheduler_status",
        "phase7_fully_accepted", "phase8_allowed",
    ]
    return "\n".join(f"{k}: {d.get(k)}" for k in keys) + "\n"


def render_markdown(report: DailyObservationReport) -> str:
    d = report.to_dict()
    lines = [
        f"# Shadow daily observation report {d['report_date_utc']} (UTC)",
        "",
        f"- report_version: `{d['report_version']}`",
        f"- overall_status: **{d['overall_status']}**",
        f"- can_count_as_valid_day: {d['can_count_as_valid_day']}",
        f"- expected_periodic_ticks: {d['expected_periodic_ticks']}",
        f"- actual_periodic_snapshots: {d['actual_periodic_snapshots']}",
        f"- manual_snapshots: {d['manual_snapshots']}",
        f"- total_snapshots: {d['total_snapshots']}",
        f"- previous_day_total: {d['previous_day_total_snapshots']}",
        f"- delta_vs_previous: {d['snapshot_delta_vs_previous_day']}",
        f"- accounts_covered: {d['accounts_covered']} / {d['accounts_expected']}",
        f"- runtime_unknown: {d['runtime_unknown_count']}",
        f"- live_state_missing: {d['live_state_missing_count']}",
        f"- high: {d['by_severity'].get('HIGH', 0)} critical: {d['by_severity'].get('CRITICAL', 0)}",
        f"- cutover_true_count: {d['cutover_true_count']}",
        f"- database: {d['database_status']} redis: {d['redis_status']} celery: {d['celery_worker_status']}",
        f"- scheduler: {d['scheduler_status']}",
        f"- phase7_fully_accepted: false",
        f"- phase8_allowed: false",
        "",
        "## By mismatch class",
    ]
    for k, v in sorted((d.get("by_mismatch_class") or {}).items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Validity reasons")
    for r in d.get("validity_reason_codes") or []:
        lines.append(f"- {r}")
    return "\n".join(lines) + "\n"
