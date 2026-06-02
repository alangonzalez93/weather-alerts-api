import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.config import settings
from app.core.celery_app import celery_app
from app.core.database_sync import get_sync_session
from app.core.redis_client import redis_client
from app.models.notification import Notification
from app.repositories.alert_sync_repository import AlertSyncRepository
from app.repositories.notification_sync_repository import NotificationSyncRepository
from app.repositories.weather_forecast_sync_repository import WeatherForecastSyncRepository
from app.tasks.deliver_notification import deliver_notification

logger = logging.getLogger(__name__)

EVAL_LOCK_KEY = "lock:evaluate_alerts"


@celery_app.task(name="evaluate_alerts")
def evaluate_alerts() -> None:
    """Periodic task: evaluates all active alerts and enqueues delivery tasks.

    Registered in celery_app.py beat schedule.
    """
    # Distributed lock — prevents concurrent runs if a cycle outlasts the interval.
    # TTL = 2 x ALERT_EVAL_INTERVAL_SECONDS so stale locks from crashed workers
    # expire before the second scheduled firing.
    lock_ttl = settings.alert_eval_interval_seconds * 2
    acquired = redis_client.set(EVAL_LOCK_KEY, "1", nx=True, ex=lock_ttl)
    if not acquired:
        logger.warning(
            "[EVALUATOR] skipping cycle — already running",
            extra={"lock_key": EVAL_LOCK_KEY},
        )
        return

    try:
        _run_evaluation()
    finally:
        redis_client.delete(EVAL_LOCK_KEY)


def _run_evaluation() -> None:
    today = datetime.now(tz=UTC).date()
    lookahead = today + timedelta(days=settings.alert_lookahead_days)
    batch_size = settings.alert_eval_batch_size

    # ── Phase 1: evaluate alerts, create pending notifications ─────────────────
    # Cursor-based pagination — O(1) seek on (is_active, id) partial index.
    # No drift: new alerts created mid-cycle are never missed or double-counted.
    after_id: UUID | None = None
    while True:
        with get_sync_session() as session:
            alert_repo = AlertSyncRepository(session)
            forecast_repo = WeatherForecastSyncRepository(session)
            notification_repo = NotificationSyncRepository(session)

            batch = alert_repo.get_active(limit=batch_size, after_id=after_id)
            if not batch:
                break

            # Pre-fetch forecasts for all unique (zone, event_type) pairs in the batch.
            # Avoids N redundant DB queries when many alerts share the same zone/event.
            zone_event_pairs = {(a.zone, a.event_type) for a in batch}
            forecast_cache = {
                (zone, event_type): forecast_repo.get_by_zone_event_date_range(
                    zone=zone,
                    event_type=event_type,
                    date_from=today,
                    date_to=lookahead,
                )
                for zone, event_type in zone_event_pairs
            }

            for alert in batch:
                try:
                    _evaluate_alert(
                        alert,
                        forecast_cache[(alert.zone, alert.event_type)],
                        notification_repo,
                        today,
                        lookahead,
                    )
                except Exception:
                    logger.exception(
                        "[EVALUATOR] alert processing failed",
                        extra={"alert_id": str(alert.id)},
                    )

            after_id = batch[-1].id

    # ── Phase 2: enqueue ALL pending notifications from DB ─────────────────────
    # Querying from DB after all batches are committed guarantees we only enqueue
    # what is already persisted. Also picks up notifications stuck in pending
    # from previous failed runs — self-healing behaviour.
    after_id = None
    total_enqueued = 0
    while True:
        with get_sync_session() as session:
            notification_repo = NotificationSyncRepository(session)
            pending = notification_repo.get_pending(limit=batch_size, after_id=after_id)
            if not pending:
                break
            for notification in pending:
                deliver_notification.delay(str(notification.id))
                total_enqueued += 1
            after_id = pending[-1].id

    logger.info(
        "[EVALUATOR] cycle complete",
        extra={"enqueued": total_enqueued, "batch_size": batch_size},
    )


def _evaluate_alert(alert, forecasts, notification_repo, date_from, date_to) -> None:
    # One query fetches the latest notification for every date in the lookahead window.
    # Avoids up to 7 per-date queries per alert — result consumed from memory below.
    latest_by_date = notification_repo.get_latest_by_dates_for_alert(
        alert.id, date_from, date_to
    )

    for forecast in forecasts:
        if forecast.probability < alert.threshold:
            continue

        last = latest_by_date.get(forecast.date)

        should_notify = last is None or (
            abs(forecast.probability - last.probability) >= settings.alert_renotify_delta
        )

        if should_notify:
            notification_repo.create(
                Notification(
                    alert_id=alert.id,
                    target_date=forecast.date,
                    probability=forecast.probability,
                )
            )
