import logging

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class HealthCheckFilter(logging.Filter):
    """Filter out health check access logs to reduce noise."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


def setup_logging(log_level: str) -> None:
    """Configure root logger. Called once at startup from main.py."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    for noisy_logger in ("httpx", "httpcore", "asyncpg", "sqlalchemy.engine"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
