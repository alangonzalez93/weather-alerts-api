import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


@runtime_checkable
class AuditFields(Protocol):
    """Structural interface — any model with AuditMixin columns satisfies this."""

    id: UUID
    deleted: bool
    updated_at: datetime.datetime


class BaseRepository[T: AuditFields]:
    """Generic async repository for FastAPI.

    Subclasses call super().__init__(ModelClass, session).
    All queries automatically filter deleted=False — concrete repositories
    never need to add this filter explicitly.
    """

    def __init__(self, model: type[T], session: AsyncSession) -> None:
        self._model = model
        self.session = session

    async def get_by_id(self, id: UUID) -> T | None:
        result = await self.session.execute(
            select(self._model).where(
                self._model.id == id,
                self._model.deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def create(self, instance: T) -> T:
        self.session.add(instance)
        # flush writes to DB within the current transaction without committing —
        # lets the caller decide when to commit (unit of work pattern)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: T) -> T:
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: T) -> None:
        instance.deleted = True
        instance.updated_at = datetime.datetime.now(datetime.UTC)
        await self.session.flush()


class SyncBaseRepository[T: AuditFields]:
    """Generic sync repository for Celery workers.

    Subclasses call super().__init__(ModelClass, session).
    All queries automatically filter deleted=False.
    """

    def __init__(self, model: type[T], session: Session) -> None:
        self._model = model
        self.session = session

    def get_by_id(self, id: UUID) -> T | None:
        result = self.session.execute(
            select(self._model).where(
                self._model.id == id,
                self._model.deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    def create(self, instance: T) -> T:
        self.session.add(instance)
        self.session.flush()
        self.session.refresh(instance)
        return instance

    def update(self, instance: T) -> T:
        self.session.flush()
        self.session.refresh(instance)
        return instance

    def delete(self, instance: T) -> None:
        instance.deleted = True
        instance.updated_at = datetime.datetime.now(datetime.UTC)
        self.session.flush()
