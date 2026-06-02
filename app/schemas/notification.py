import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import NotificationStatus


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alert_id: UUID
    target_date: datetime.date
    probability: float
    status: NotificationStatus
    triggered_at: datetime.datetime
