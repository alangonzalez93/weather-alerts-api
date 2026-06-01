import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_async_session
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> HealthResponse:
    db_ok = await _check_database(session)
    redis_ok = await _check_redis()

    if not db_ok or not redis_ok:
        response.status_code = 503

    return HealthResponse(
        status="ok" if (db_ok and redis_ok) else "error",
        database="ok" if db_ok else "unreachable",
        redis="ok" if redis_ok else "unreachable",
    )


async def _check_database(session: AsyncSession) -> bool:
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    try:
        client = aioredis.from_url(settings.celery_broker_url)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False
