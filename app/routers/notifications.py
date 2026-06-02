import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.models.enums import NotificationStatus
from app.schemas.common import PaginatedResponse
from app.schemas.notification import NotificationResponse
from app.services import notification_service

router = APIRouter(prefix="/alerts", tags=["notifications"])


@router.get("/{alert_id}/notifications", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    alert_id: UUID,
    status: NotificationStatus | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[NotificationResponse]:
    notifications, total = await notification_service.list_notifications(
        alert_id=alert_id,
        status_filter=status,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
        session=session,
    )
    return PaginatedResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        limit=limit,
        offset=offset,
    )
