import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.config.logging import setup_logging
from app.core.exceptions import unhandled_exception_handler
from app.routers import alerts, health, notifications

# Called at module level so logging is ready before any import side effects
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("[APP][STARTUP]", extra={"env": settings.env})
    yield
    logger.info("[APP][SHUTDOWN]")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Weather Alerts API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health.router)
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")

    return app


app = create_app()
