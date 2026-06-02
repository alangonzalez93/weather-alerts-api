import logging
import random
from uuid import UUID

from celery.exceptions import MaxRetriesExceededError

from app.core.celery_app import celery_app
from app.core.database_sync import get_sync_session
from app.models.enums import NotificationStatus
from app.repositories.alert_sync_repository import AlertSyncRepository
from app.repositories.notification_sync_repository import NotificationSyncRepository

logger = logging.getLogger(__name__)


@celery_app.task(
    name="deliver_notification",
    bind=True,
    max_retries=3,
)
def deliver_notification(self, notification_id: str) -> None:
    with get_sync_session() as session:
        notification_repo = NotificationSyncRepository(session)
        notification = notification_repo.get_by_id(UUID(notification_id))

        if notification is None or notification.status != NotificationStatus.pending:
            return  # already delivered or soft-deleted — idempotent skip

        alert_repo = AlertSyncRepository(session)
        alert = alert_repo.get_by_id(notification.alert_id)
        if alert is None:
            return  # alert was soft-deleted after notification was created

        try:
            _deliver(notification, alert)
            notification_repo.update_status(notification, NotificationStatus.sent)
        except Exception as exc:
            # Exponential backoff with jitter: ~60s, ~120s, ~240s.
            # Jitter prevents thundering herds when many notifications fail simultaneously.
            delay = 60 * (2 ** self.request.retries) + random.uniform(0, 30)
            try:
                raise self.retry(exc=exc, countdown=delay)
            except MaxRetriesExceededError:
                notification_repo.update_status(notification, NotificationStatus.failed)
                logger.exception(
                    "[DELIVERY] max retries exceeded",
                    extra={"notification_id": notification_id},
                )


def _build_message(notification, alert) -> str:
    pct = round(notification.probability * 100)
    event = alert.event_type.replace("_", " ")
    return (
        f"Weather alert for zone '{alert.zone}': {event} forecast on {notification.target_date} "
        f"with {pct}% probability — exceeds your configured threshold of "
        f"{round(alert.threshold * 100)}%. Take the necessary precautions."
    )


def _deliver(notification, alert) -> None:
    message = _build_message(notification, alert)
    channel = alert.notification_channel

    if channel == "whatsapp":
        logger.info(
            "[DELIVERY] WhatsApp → %s | alert=%s | %s",
            alert.contact,
            notification.alert_id,
            message,
            extra={
                "channel": channel,
                "contact": alert.contact,
                "alert_id": str(notification.alert_id),
                "target_date": str(notification.target_date),
                "probability": notification.probability,
            },
        )
    elif channel == "email":
        logger.info(
            "[DELIVERY] Email → %s | alert=%s | %s",
            alert.contact,
            notification.alert_id,
            message,
            extra={
                "channel": channel,
                "contact": alert.contact,
                "alert_id": str(notification.alert_id),
                "target_date": str(notification.target_date),
                "probability": notification.probability,
            },
        )
