from celery import Celery
from celery.schedules import crontab
from kombu import Queue
from app.config import settings

celery_app = Celery("whatsapp_sender", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"],
    timezone="Asia/Tehran", enable_utc=True, worker_prefetch_multiplier=1, task_acks_late=True)

# ── A2: per-queue task isolation (scaling to 80 accounts) ──────────────────
# Route task types to dedicated queues so one slow/banned account or a heavy
# extraction can't starve campaign sends or webhook polling. Workers consume
# specific queues (see docker-compose worker-* services).
celery_app.conf.task_queues = (
    Queue("campaigns"),
    Queue("sending"),     # reserved for the per-account send subtasks (future)
    Queue("webhooks"),
    Queue("extraction"),
    Queue("backfill"),
    Queue("celery"),      # default (beat/maintenance tasks)
)
celery_app.conf.task_default_queue = "celery"
celery_app.conf.task_routes = {
    "tasks.run_campaign": {"queue": "campaigns"},
    "tasks.run_group_campaign": {"queue": "campaigns"},
    "tasks.poll_accounts": {"queue": "webhooks"},
    "tasks.extract_all_groups": {"queue": "extraction"},
    "tasks.backfill_group_member_counts": {"queue": "backfill"},
}

celery_app.conf.beat_schedule = {
    # Fires at 00:00 Tehran (app timezone is Asia/Tehran) — resilient to worker
    # restarts, unlike a plain 86400s interval whose timer resets on each restart.
    "reset-daily-counters": {"task": "tasks.reset_daily_counters", "schedule": crontab(hour=0, minute=0)},
    # Daily status post + warm-up increment at 10:00 Tehran (once per day)
    "warmup-accounts": {"task": "tasks.warmup_accounts", "schedule": crontab(hour=10, minute=0)},
    "sync-account-states": {"task": "tasks.sync_account_states", "schedule": 300.0},
    "poll-accounts": {"task": "tasks.poll_accounts", "schedule": 10.0},
    "clear-product-mentions": {"task": "tasks.clear_old_product_mentions", "schedule": 86400.0},
    "backfill-group-members": {"task": "tasks.backfill_group_member_counts", "schedule": 21600.0},  # every 6h
    "recover-orphaned-campaigns": {"task": "tasks.recover_orphaned_campaigns", "schedule": 600.0},  # every 10 min
    "check-status-schedules": {"task": "tasks.check_status_schedules", "schedule": 300.0},  # every 5 min
    "recheck-ai-keys": {"task": "tasks.recheck_ai_keys", "schedule": 1800.0},  # every 30 min — auto-recover keys
    # V13.8 — resume drip campaigns at the start of the daily send window (Tehran)
    "resume-drip-campaigns": {"task": "tasks.resume_drip_campaigns", "schedule": crontab(hour=8, minute=1)},
    # 23:00 Tehran (celery timezone is Asia/Tehran, so crontab is interpreted there)
    "night-report": {"task": "tasks.send_night_report", "schedule": crontab(hour=23, minute=0)},
    # V14 F3 — reconcile local accounts with the Green API Partner list every 6h.
    "sync-partner-instances": {"task": "tasks.sync_partner_instances", "schedule": 21600.0},
    # V14 F23 — poll for yellowCard every 2 min (webhooks can be missed if the tunnel dies).
    "detect-yellow-cards": {"task": "tasks.detect_yellow_cards", "schedule": 120.0},
    # V27 PART 4 — real-time instance-state monitoring: refresh the live-state cache the
    # pre-send gate reads every ~60s and quarantine danger states immediately (getStateInstance
    # GET only — webhook-only message receipt is untouched).
    "poll-instance-states": {"task": "tasks.poll_instance_states", "schedule": 60.0},
    # V14 F24 — pull call journals every 30 min.
    "sync-call-logs": {"task": "tasks.sync_call_logs", "schedule": 1800.0},
    # V14 F23.6 — reply-rate monitor hourly.
    "reply-rate-monitor": {"task": "tasks.reply_rate_monitor", "schedule": 3600.0},
    # V14 PART G — weekly re-probe of safe read-only methods (604800s = 7 days).
    "recheck-method-support": {"task": "tasks.recheck_method_support", "schedule": 604800.0},
    # V15/V16 — managed auto warm-up. Runs several times a day (Tehran) so sends are spread
    # human-like across the day; the Redis daily counter enforces the per-stage cap.
    "process-warmup-accounts": {"task": "tasks.process_warmup_accounts",
                                "schedule": crontab(hour="9,11,13,16,19", minute=0)},
    # V17 PART 4 — automatic jittered AI mesh warm-up engine. A frequent tick lets each
    # number run its OWN randomized schedule; the tick itself does nothing outside a
    # number's jittered next_action_at / active hours.
    "process-mesh-warmup": {"task": "tasks.process_mesh_warmup", "schedule": 180.0},
    # V17 PART 5 — reset/erosion detection: restart warm-up for numbers idle past 14/30 days.
    "warmup-safety-scan": {"task": "tasks.warmup_safety_scan", "schedule": 21600.0},  # every 6h
    # V19 PART 4 — automatic group placement (ADDITIVE to the mesh). Frequent tick; the fixed
    # schedule itself caps this to ≤1 group action per cold number per day.
    "process-group-warmup": {"task": "tasks.process_group_warmup", "schedule": 600.0},  # every 10 min
    # V25 PART 1 — automatic human-helper warm-up assist. Frequent tick; each tick sends AT
    # MOST one helper-ask/reminder, gated by waking hours + the jittered rate limiter, so the
    # main account is never blasted. Default OFF (no-op until the toggle is enabled).
    "process-helper-warmup": {"task": "tasks.process_helper_warmup", "schedule": 180.0},
}
