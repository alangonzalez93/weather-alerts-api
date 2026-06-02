from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.schemas.alert import AlertCreate, AlertResponse, AlertUpdate
from app.schemas.common import PaginatedResponse
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    data: AlertCreate,
    session: AsyncSession = Depends(get_async_session),
) -> AlertResponse:
    alert = await alert_service.create(data, session)
    return AlertResponse.model_validate(alert)


@router.get("/", response_model=PaginatedResponse[AlertResponse])
async def list_alerts(
    field_id: UUID,
    is_active: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[AlertResponse]:
    alerts, total = await alert_service.list_alerts(
        field_id=field_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
        session=session,
    )
    return PaginatedResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> AlertResponse:
    alert = await alert_service.get(alert_id, session)
    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: UUID,
    data: AlertUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> AlertResponse:
    alert = await alert_service.update(alert_id, data, session)
    return AlertResponse.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    await alert_service.delete(alert_id, session)
