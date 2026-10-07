"""Celery app. Broker + backend: Redis. Beat schedule = the daily routine (M1+)."""
from celery import Celery

from app.config import settings

celery = Celery("aibos", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "m0-healthcheck": {"task": "worker.tasks.healthcheck", "schedule": 300.0},
        # M1: daily shadow routine 09:00 Asia/Karachi (configurable in M2)
        "m1-daily-routine": {"task": "worker.tasks.daily_routine",
                             "schedule": 86400.0},
    },
)
celery.autodiscover_tasks(["worker"])
