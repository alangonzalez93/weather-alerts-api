from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base_model import AuditMixin
from app.models.enums import NotificationChannel, WeatherEventType


class Alert(AuditMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "threshold >= 0.0 AND threshold <= 1.0",
            name="ck_alerts_threshold",
        ),
        # API list query: filters by field + active status, ordered result in one B-tree pass
        Index("ix_alerts_field_id_is_active_created_at", "field_id", "is_active", "created_at"),
        # Evaluator cursor scan: forward traversal over active non-deleted alerts by id
        Index(
            "ix_alerts_is_active_id",
            "is_active",
            "id",
            postgresql_where="deleted = false",
        ),
        # Evaluator forecast lookup
        Index("ix_alerts_zone_event_type", "zone", "event_type"),
    )

    # Logical reference to the client's field — no FK, cross-service UUID reference
    field_id: Mapped[UUID] = mapped_column()
    zone: Mapped[str] = mapped_column(String(100))
    # Stored as VARCHAR(50) — enum validated in Python, not at DB level
    event_type: Mapped[WeatherEventType] = mapped_column(String(50))
    threshold: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # VARCHAR(20) — whatsapp | email
    notification_channel: Mapped[NotificationChannel] = mapped_column(String(20))
    # E.164 phone for whatsapp, email address for email — validated at API layer
    contact: Mapped[str] = mapped_column(String(255))
