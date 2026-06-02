from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Alert, session)

    async def list(
        self,
        field_id: UUID,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Alert], int]:
        base_where = [
            Alert.field_id == field_id,
            Alert.deleted == False,  # noqa: E712
        ]
        if is_active is not None:
            base_where.append(Alert.is_active == is_active)

        count_result = await self.session.execute(
            select(func.count()).select_from(Alert).where(*base_where)
        )
        total = count_result.scalar_one()

        rows_result = await self.session.execute(
            select(Alert)
            .where(*base_where)
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(rows_result.scalars().all())

        return rows, total
