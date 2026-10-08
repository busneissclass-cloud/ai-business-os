"""Celery app. Broker + backend: Redis. Beat schedule = the daily routine (M1+)."""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery = Celery("aibos", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    timezone="Asia/Karachi",
    beat_schedule={
        "m0-healthcheck": {"task": "worker.tasks.healthcheck", "schedule": 300.0},
        # M1: daily shadow routine at 09:00 Asia/Karachi
        "m1-daily-routine": {"task": "worker.tasks.daily_routine",
                             "schedule": crontab(hour=9, minute=0)},
    },
)
celery.autodiscover_tasks(["worker"])
