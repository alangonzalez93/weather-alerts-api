import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from app.core.database import Base, get_async_session
from app.main import app


@pytest.fixture(scope="session")
def postgres_url():
    """Start a real Postgres container once for the entire test session."""
    with PostgresContainer("postgres:16-alpine") as container:
        yield container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )


@pytest.fixture(scope="session", autouse=True)
def create_schema(postgres_url):
    """Create all tables once using a sync engine — avoids event loop conflicts
    between session-scoped setup and function-scoped async test loops."""
    sync_url = postgres_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    engine = create_engine(sync_url)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
async def db_session(postgres_url, create_schema):
    """Each test gets a fresh async engine bound to its own event loop.

    The transaction is rolled back on teardown — the DB is clean for the next test.
    """
    engine = create_async_engine(postgres_url, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    yield session
    await session.close()
    await transaction.rollback()
    await connection.close()
    await engine.dispose()


@pytest.fixture
async def client(db_session):
    """HTTP client with the DB dependency overridden to use the test session.

    FastAPI's DI is bypassed so every request shares the same rolled-back transaction.
    """

    async def _override():
        yield db_session

    app.dependency_overrides[get_async_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
