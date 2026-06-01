# Design — Project Base Setup

## Stack

| Component          | Technology                      | Rationale |
|--------------------|---------------------------------|-----------|
| Framework          | FastAPI                         | Native async, automatic OpenAPI, high performance |
| Package manager    | uv                              | Faster dependency resolution than pip/poetry, modern standard |
| ORM (async)        | SQLAlchemy 2.x + asyncpg        | Async sessions for FastAPI endpoints |
| ORM (sync)         | SQLAlchemy 2.x + psycopg2       | Sync sessions for Celery workers |
| Database           | PostgreSQL 16                   | ACID, native UUID/TIMESTAMPTZ support |
| Migrations         | Alembic                         | Native SQLAlchemy integration, versioned migrations |
| Validation/config  | Pydantic v2 + pydantic-settings | Typed env var validation, request/response schemas |
| Task queue         | Celery                          | Industry standard for distributed tasks in Python |
| Broker             | Redis                           | Low overhead, simple to operate, Celery-compatible |
| Containerization   | Docker + Docker Compose         | Reproducible environment, one command to run everything |
| Logging            | structlog                       | Structured logging (JSON in prod, readable in dev) |

---

## Layered Architecture

```
┌─────────────────────────────────────────┐
│              Routers (HTTP)             │  ← request/response, HTTP status codes
├─────────────────────────────────────────┤
│             Services (logic)            │  ← business rules, orchestration
├─────────────────────────────────────────┤
│          Repositories (data)            │  ← all DB queries, no business logic
├─────────────────────────────────────────┤
│            Models (ORM)                 │  ← table definitions only
└─────────────────────────────────────────┘
```

Each layer only knows about the layer directly below it. Routers never touch repositories. Services never build HTTP responses.

## Project Structure

```
weather-alerts-api/
├── pyproject.toml              # Dependencies + metadata + tool config
├── uv.lock                     # Reproducible lockfile
├── .env.example                # Documented environment variables
├── .env                        # Local variables (gitignored)
├── Dockerfile                  # Multi-stage build
├── docker-compose.yml          # Production services
├── docker-compose.override.yml # Local development overrides
├── alembic.ini
├── alembic/
│   ├── env.py                  # Async Alembic configuration
│   └── versions/
│       └── 0001_initial.py     # Initial migration: weather_records
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory + routers + lifespan
│   ├── config.py               # Settings via pydantic-settings
│   ├── database.py             # Async engine + async session factory
│   ├── database_sync.py        # Sync engine + sync session factory
│   ├── celery_app.py           # Celery app + beat schedule
│   ├── models/
│   │   ├── __init__.py         # Enums: WeatherEventType, NotificationStatus
│   │   └── weather_record.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py             # Generic BaseRepository[T]
│   │   └── weather_record_repository.py
│   ├── schemas/
│   │   └── __init__.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── health.py           # GET /health
│   ├── services/
│   │   └── __init__.py
│   ├── tasks/
│   │   └── __init__.py
│   └── scripts/
│       └── seed_weather.py
├── specs/
└── tests/
    └── conftest.py
```

## Repository Pattern

### Base Repository

Generic base using Python 3.12 type parameters. All concrete repositories inherit from it.

```python
class BaseRepository[T]:
    def __init__(self, session: AsyncSession | Session) -> None:
        self.session = session

    async def get_by_id(self, id: UUID) -> T | None: ...
    async def create(self, instance: T) -> T: ...
    async def update(self, instance: T) -> T: ...
    async def delete(self, instance: T) -> None: ...
```

The same repository classes accept both `AsyncSession` (FastAPI) and `Session` (Celery) — the caller is responsible for passing the appropriate session type.

### `WeatherRecordRepository`

```python
class WeatherRecordRepository(BaseRepository[WeatherRecord]):
    async def upsert(self, record: WeatherRecord) -> WeatherRecord: ...
    async def get_by_zone_event_date_range(
        self, zone: str, event_type: WeatherEventType,
        date_from: date, date_to: date
    ) -> list[WeatherRecord]: ...
```

---

## pyproject.toml

```toml
[project]
name = "weather-alerts-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]",
    "sqlalchemy[asyncio]",
    "asyncpg",
    "psycopg2-binary",
    "alembic",
    "pydantic-settings",
    "celery[redis]",
    "redis",
    "structlog",
]

[dependency-groups]
dev = [
    "pytest",
    "pytest-asyncio",
    "httpx",
    "ruff",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Environment Variables

```bash
# .env.example

# Database
DATABASE_URL=postgresql+asyncpg://agrobot:agrobot@db:5432/weather_alerts_api
DATABASE_URL_SYNC=postgresql+psycopg2://agrobot:agrobot@db:5432/weather_alerts_api

# Redis / Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Alert Evaluator
ALERT_EVAL_INTERVAL_SECONDS=3600
ALERT_LOOKAHEAD_DAYS=7
ALERT_RENOTIFY_DELTA=0.10

# App
ENV=development   # development | production
LOG_LEVEL=INFO
```

---

## Data Model — `weather_records`

### Enum: `WeatherEventType` (Python `str` enum, `VARCHAR` column in DB)

Defined in code. The PostgreSQL column is `VARCHAR(50)` — adding a new value requires no migration.

```
frost        → Frost
rain         → Rain
heavy_rain   → Heavy rain
hail         → Hail
storm        → Thunderstorm
drought      → Drought
heat_wave    → Heat wave
strong_wind  → Strong wind
flood        → Flood
```

### Table

| Column        | Type         | Constraints                       |
|---------------|--------------|-----------------------------------|
| `id`          | UUID         | PK, default gen_random_uuid()     |
| `zone`        | VARCHAR(100) | NOT NULL                          |
| `date`        | DATE         | NOT NULL                          |
| `event_type`  | VARCHAR(50)  | NOT NULL                          |
| `probability` | FLOAT        | NOT NULL, CHECK (0.0 <= x <= 1.0) |
| `updated_at`  | TIMESTAMPTZ  | NOT NULL                          |
| `created_at`  | TIMESTAMPTZ  | NOT NULL, default now()           |

**Constraints:**
- UNIQUE `(zone, date, event_type)`

**Indexes:**
- `(zone, date)` — range lookup by the alert evaluator

---

## Docker

### Services (`docker-compose.yml`)

```
┌─────────┐  ┌─────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   db    │  │  redis  │  │     api      │  │    worker    │  │     beat     │
│ Postgres│  │  Redis  │  │   FastAPI    │  │Celery Worker │  │ Celery Beat  │
│  :5432  │  │  :6379  │  │    :8000     │  │              │  │              │
└─────────┘  └─────────┘  └──────────────┘  └──────────────┘  └──────────────┘
     ▲              ▲            ▲  ▲               ▲  ▲               ▲
     └──────────────┘            │  └───────────────┘  └───────────────┘
                                 │         (depends_on: db, redis)
                          runs migrations
                          on startup
```

### Dockerfile (multi-stage)

```
Stage 1 (builder):
  - python:3.12-slim
  - install uv
  - install dependencies into /app/.venv

Stage 2 (runtime):
  - python:3.12-slim
  - copy .venv from builder
  - copy source code
  - non-root user
  - CMD: uvicorn app.main:app
```

### Service commands

| Service  | Command |
|----------|---------|
| `api`    | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `worker` | `celery -A app.celery_app worker --loglevel=info` |
| `beat`   | `celery -A app.celery_app beat --loglevel=info` |

---

## API — Health Check

#### `GET /health`

```
Response 200 → { "status": "ok", "database": "ok" }
Response 503 → { "status": "error", "database": "unreachable" }
```

Verifies PostgreSQL connectivity by executing a trivial query (`SELECT 1`).
