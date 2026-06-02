import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import NotificationStatus
from app.models.notification import Notification
from app.repositories.base import SyncBaseRepository


class NotificationSyncRepository(SyncBaseRepository[Notification]):
    def __init__(self, session: Session) -> None:
        super().__init__(Notification, session)

    def get_latest_by_dates_for_alert(
        self,
        alert_id: UUID,
        date_from: datetime.date,
        date_to: datetime.date,
    ) -> dict[datetime.date, Notification | None]:
        """Single query returning the most recent non-deleted notification per date.

        Uses DISTINCT ON (target_date) ordered by triggered_at DESC — PostgreSQL-specific.
        Overall cost is O(N log N) on the rows for this alert in the date range, but returns
        exactly one row per date. Result consumed in memory by _evaluate_alert to avoid
        N individual per-date queries.
        """
        stmt = (
            select(Notification)
            .where(
                Notification.alert_id == alert_id,
                Notification.target_date >= date_from,
                Notification.target_date <= date_to,
                Notification.deleted == False,  # noqa: E712
            )
            .distinct(Notification.target_date)
            .order_by(Notification.target_date, Notification.triggered_at.desc())
        )
        rows = list(self.session.execute(stmt).scalars().all())
        return {n.target_date: n for n in rows}

    def get_pending(
        self,
        limit: int,
        after_id: UUID | None,
    ) -> list[Notification]:
        """Cursor-based fetch of pending non-deleted notifications ordered by id."""
        where_clauses = [
            Notification.status == NotificationStatus.pending,
            Notification.deleted == False,  # noqa: E712
        ]
        if after_id is not None:
            where_clauses.append(Notification.id > after_id)

        result = self.session.execute(
            select(Notification)
            .where(*where_clauses)
            .order_by(Notification.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def update_status(self, notification: Notification, status: NotificationStatus) -> None:
        """ORM-level update — idiomatic for single-record state transitions."""
        notification.status = status
        notification.updated_at = datetime.datetime.now(datetime.UTC)
        self.session.flush()
