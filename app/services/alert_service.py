import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.repositories.alert_repository import AlertRepository
from app.repositories.notification_repository import NotificationRepository
from app.schemas.alert import AlertCreate, AlertUpdate


async def create(data: AlertCreate, session: AsyncSession) -> Alert:
    repo = AlertRepository(session)
    alert = Alert(
        field_id=data.field_id,
        zone=data.zone,
        event_type=data.event_type,
        threshold=data.threshold,
        notification_channel=data.notification_channel,
        contact=data.contact,
    )
    return await repo.create(alert)


async def get(alert_id: UUID, session: AsyncSession) -> Alert:
    repo = AlertRepository(session)
    alert = await repo.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


async def list_alerts(
    field_id: UUID,
    is_active: bool | None,
    limit: int,
    offset: int,
    session: AsyncSession,
) -> tuple[list[Alert], int]:
    repo = AlertRepository(session)
    return await repo.list(field_id=field_id, is_active=is_active, limit=limit, offset=offset)


async def update(alert_id: UUID, data: AlertUpdate, session: AsyncSession) -> Alert:
    repo = AlertRepository(session)
    alert = await repo.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    if data.threshold is not None:
        alert.threshold = data.threshold
    if data.is_active is not None:
        alert.is_active = data.is_active
    if data.contact is not None:
        alert.contact = data.contact
    if data.notification_channel is not None:
        alert.notification_channel = data.notification_channel

    alert.updated_at = datetime.datetime.now(datetime.UTC)
    return await repo.update(alert)


async def delete(alert_id: UUID, session: AsyncSession) -> None:
    alert_repo = AlertRepository(session)
    notification_repo = NotificationRepository(session)

    alert = await alert_repo.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    # Both operations use the same session — they commit together atomically.
    # Never instantiate separate sessions for these two steps.
    await notification_repo.soft_delete_pending_by_alert(alert_id)
    await alert_repo.delete(alert)
