from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery("whatsapp_sender", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"],
    timezone="Asia/Tehran", enable_utc=True, worker_prefetch_multiplier=1, task_acks_late=True)

celery_app.conf.beat_schedule = {
    "reset-daily-counters": {"task": "tasks.reset_daily_counters", "schedule": 86400.0},
    "warmup-accounts": {"task": "tasks.warmup_accounts", "schedule": 3600.0},
    "sync-account-states": {"task": "tasks.sync_account_states", "schedule": 300.0},
    "poll-accounts": {"task": "tasks.poll_accounts", "schedule": 10.0},
    "clear-product-mentions": {"task": "tasks.clear_old_product_mentions", "schedule": 86400.0},
    # 23:00 Tehran (celery timezone is Asia/Tehran, so crontab is interpreted there)
    "night-report": {"task": "tasks.send_night_report", "schedule": crontab(hour=23, minute=0)},
}
