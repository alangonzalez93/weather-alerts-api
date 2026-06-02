import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationStatus
from app.models.notification import Notification
from app.repositories.alert_repository import AlertRepository
from app.repositories.notification_repository import NotificationRepository


async def list_notifications(
    alert_id: UUID,
    status_filter: NotificationStatus | None,
    from_date: datetime.date | None,
    to_date: datetime.date | None,
    limit: int,
    offset: int,
    session: AsyncSession,
) -> tuple[list[Notification], int]:
    alert_repo = AlertRepository(session)
    alert = await alert_repo.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    notification_repo = NotificationRepository(session)
    return await notification_repo.list_by_alert(
        alert_id=alert_id,
        status=status_filter,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
