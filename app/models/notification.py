import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base_model import AuditMixin
from app.models.enums import NotificationStatus


class Notification(AuditMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # Evaluator deduplication lookup: (alert_id, target_date) → most recent notification
        Index("ix_notifications_alert_id_target_date", "alert_id", "target_date"),
        # API list filtering + soft_delete_pending_by_alert bulk update
        Index(
            "ix_notifications_alert_id_status",
            "alert_id",
            "status",
            postgresql_where="deleted = false",
        ),
        # Evaluator Phase 2 cursor scan over pending notifications
        Index(
            "ix_notifications_status_id",
            "status",
            "id",
            postgresql_where="deleted = false",
        ),
    )

    # ON DELETE RESTRICT: physical deletes of alerts must never happen.
    # App exclusively soft-deletes — RESTRICT ensures a direct DB DELETE fails loudly
    # rather than silently cascade-wiping historical notification records.
    alert_id: Mapped[UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False
    )
    target_date: Mapped[datetime.date] = mapped_column()
    probability: Mapped[float] = mapped_column(Float)
    # status transitions: pending → sent | failed. Write-once from user perspective.
    status: Mapped[NotificationStatus] = mapped_column(
        String(20), server_default=NotificationStatus.pending
    )
    triggered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
