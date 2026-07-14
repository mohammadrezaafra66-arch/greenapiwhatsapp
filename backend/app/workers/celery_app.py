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
}
