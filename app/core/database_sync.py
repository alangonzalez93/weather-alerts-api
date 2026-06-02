from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

sync_engine = create_engine(
    settings.database_url_sync,
    pool_pre_ping=True,
    pool_size=settings.db_worker_pool_size,
    max_overflow=settings.db_worker_max_overflow,
    pool_recycle=settings.db_pool_recycle,
)

SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Context manager that commits on success and rolls back on any exception.

    Commit/rollback responsibility lives here so callers never forget it.
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
