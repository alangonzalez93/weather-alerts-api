from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str
    # API pool — handles concurrent async requests.
    # Total API connections = (db_pool_size + db_max_overflow) x api_processes.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # Worker pool — each worker processes one task at a time (prefetch=1),
    # so it needs at most 1 active connection. A small pool avoids holding
    # idle connections that eat into Postgres max_connections for nothing.
    # Total worker connections = (db_worker_pool_size + db_worker_max_overflow) x num_workers.
    db_worker_pool_size: int = 2
    db_worker_max_overflow: int = 3
    # Recycle connections idle > 1h to avoid stale sockets after DB restarts
    db_pool_recycle: int = 3600

    # Celery / Redis
    celery_broker_url: str
    celery_result_backend: str

    # Alert evaluator
    alert_eval_interval_seconds: int = 3600
    alert_lookahead_days: int = 7
    alert_renotify_delta: float = 0.10
    alert_eval_batch_size: int = 500

    # Redis (used for distributed lock in evaluate_alerts)
    redis_url: str = "redis://redis:6379/0"

    # App
    env: str = "development"
    log_level: str = "INFO"

    @property
    def database_url_sync(self) -> str:
        # Derives the sync URL from the async one — single source of truth for DB credentials
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    @property
    def is_production(self) -> bool:
        return self.env == "production"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


settings = get_settings()
