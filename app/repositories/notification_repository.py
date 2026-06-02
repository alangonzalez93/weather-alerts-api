import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationStatus
from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Notification, session)

    async def list_by_alert(
        self,
        alert_id: UUID,
        status: NotificationStatus | None,
        from_date: datetime.date | None,
        to_date: datetime.date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        base_where = [
            Notification.alert_id == alert_id,
            Notification.deleted == False,  # noqa: E712
        ]
        if status is not None:
            base_where.append(Notification.status == status)
        if from_date is not None:
            base_where.append(Notification.target_date >= from_date)
        if to_date is not None:
            base_where.append(Notification.target_date <= to_date)

        count_result = await self.session.execute(
            select(func.count()).select_from(Notification).where(*base_where)
        )
        total = count_result.scalar_one()

        rows_result = await self.session.execute(
            select(Notification)
            .where(*base_where)
            .order_by(Notification.triggered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(rows_result.scalars().all())

        return rows, total

    async def soft_delete_pending_by_alert(self, alert_id: UUID) -> None:
        # Single Core UPDATE statement — O(1) DB round-trip regardless of row count.
        # Never iterate ORM row-by-row for bulk operations.
        await self.session.execute(
            update(Notification)
            .where(
                Notification.alert_id == alert_id,
                Notification.status == NotificationStatus.pending,
                Notification.deleted == False,  # noqa: E712
            )
            .values(deleted=True, updated_at=datetime.datetime.now(datetime.UTC))
        )
