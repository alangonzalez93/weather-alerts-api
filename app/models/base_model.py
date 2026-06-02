import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class AuditMixin:
    """Shared columns for all ORM models.

    Inherit as: class MyModel(AuditMixin, Base):
    The mixin must come before Base in the MRO so mapped_column declarations
    are picked up by SQLAlchemy's declarative system.
    """

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    deleted: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # onupdate intentionally absent: ORM hooks don't fire on Core bulk statements.
    # Every update path must set updated_at explicitly.
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
