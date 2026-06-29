from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "whatsapp_sender",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Tehran",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # One task at a time
    task_acks_late=True,
)

# Periodic schedule (celery beat)
celery_app.conf.beat_schedule = {
    "reset-daily-counters-midnight": {
        "task": "tasks.reset_daily_counters",
        "schedule": crontab(hour=0, minute=5),
    },
    "update-daily-limits-hourly": {
        "task": "tasks.update_daily_limits",
        "schedule": crontab(minute=0),
    },
}
