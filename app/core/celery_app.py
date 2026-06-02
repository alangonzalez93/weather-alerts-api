from celery import Celery

from app.config import settings

celery_app = Celery(
    "weather_alerts",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.evaluate_alerts",
        "app.tasks.deliver_notification",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Allows monitoring tools to observe in-progress tasks
    task_track_started=True,
    # Acknowledge tasks only after successful completion, not on receipt.
    # If a worker crashes mid-execution the task is returned to the queue.
    task_acks_late=True,
    # Re-queue tasks whose worker process was killed (OOM, SIGKILL, etc.)
    task_reject_on_worker_lost=True,
    # prefetch=1 prevents a slow task from blocking other slots on the same worker
    worker_prefetch_multiplier=1,
    beat_schedule={
        "evaluate-alerts": {
            "task": "evaluate_alerts",
            "schedule": settings.alert_eval_interval_seconds,
        }
    },
)
