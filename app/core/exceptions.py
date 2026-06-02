import logging
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions.

    Logs the full traceback with a unique error_id so it can be correlated
    across logs without exposing internals to the client.
    """
    error_id = str(uuid.uuid4())
    logger.error(
        "[ERROR][UNHANDLED] request failed",
        exc_info=exc,
        extra={
            "error_id": error_id,
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_id": error_id},
    )
