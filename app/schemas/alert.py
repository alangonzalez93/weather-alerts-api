import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import NotificationChannel, WeatherEventType

_E164_RE = re.compile(r"^\+\d{7,15}$")


def _validate_contact(channel: NotificationChannel, contact: str) -> None:
    if channel == NotificationChannel.whatsapp:
        if not _E164_RE.match(contact):
            raise ValueError("contact must be a valid E.164 phone number (e.g. +5491112345678)")
    elif channel == NotificationChannel.email:
        if "@" not in contact or "." not in contact.split("@")[-1]:
            raise ValueError("contact must be a valid email address")


class AlertCreate(BaseModel):
    field_id: UUID
    zone: str = Field(min_length=1, max_length=100)
    event_type: WeatherEventType
    threshold: float = Field(ge=0.0, le=1.0)
    notification_channel: NotificationChannel
    contact: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_contact_format(self) -> "AlertCreate":
        _validate_contact(self.notification_channel, self.contact)
        return self


class AlertUpdate(BaseModel):
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool | None = None
    contact: str | None = Field(default=None, min_length=1, max_length=255)
    notification_channel: NotificationChannel | None = None

    @model_validator(mode="after")
    def validate_contact_format(self) -> "AlertUpdate":
        if self.notification_channel is not None or self.contact is not None:
            if self.notification_channel is None or self.contact is None:
                raise ValueError("contact and notification_channel must both be provided together")
            _validate_contact(self.notification_channel, self.contact)
        return self


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    field_id: UUID
    zone: str
    event_type: WeatherEventType
    threshold: float
    is_active: bool
    notification_channel: NotificationChannel
    contact: str
    created_at: datetime
    updated_at: datetime
