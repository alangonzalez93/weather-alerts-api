from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.repositories.base import SyncBaseRepository


class AlertSyncRepository(SyncBaseRepository[Alert]):
    def __init__(self, session: Session) -> None:
        super().__init__(Alert, session)

    def get_active(self, limit: int, after_id: UUID | None) -> list[Alert]:
        """Cursor-based fetch of active non-deleted alerts ordered by id.

        after_id=None starts from the beginning.
        Use the last batch's final id as after_id on subsequent calls.
        Avoids OFFSET — O(1) seek on (is_active, id) partial index.
        """
        where_clauses = [
            Alert.is_active == True,  # noqa: E712
            Alert.deleted == False,  # noqa: E712
        ]
        if after_id is not None:
            where_clauses.append(Alert.id > after_id)

        result = self.session.execute(
            select(Alert).where(*where_clauses).order_by(Alert.id.asc()).limit(limit)
        )
        return list(result.scalars().all())
