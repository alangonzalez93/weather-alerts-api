# Tasks — Project Base Setup

Each task references the requirements it satisfies. Tasks marked with `[P]` within a phase can be executed in parallel.

---

## Phase 1 — Project Structure and Configuration

- [x] **1.1** Create project directory structure (`app/`, `tests/`, `alembic/`, `specs/`)
- [x] **1.2** Create `pyproject.toml` with production and development dependencies, ruff and pytest config → satisfies US-1.1
- [x] **1.3** Create `.env.example` with all variables documented → satisfies US-1.1
- [x] **1.4** Implement `app/config/settings.py` with `pydantic-settings` (all variables typed, fail-fast on missing) → satisfies US-1.1
- [x] **1.5** Configure Python stdlib logging in `app/config/logging.py` (`setup_logging()`, `HealthCheckFilter`, noisy logger suppression) → satisfies US-6.1

---

## Phase 2 — Database `[P]`

> Prerequisite: Phase 1 complete.

- [x] **2.1** `[P]` Implement `app/core/database.py` (async engine + `AsyncSession` factory, `get_async_session` dependency) → satisfies US-2.1
- [x] **2.2** `[P]` Implement `app/core/database_sync.py` (sync engine + `Session` factory, `get_sync_session` context manager) → satisfies US-2.1
- [x] **2.3** Initialize Alembic (`alembic init`) and configure `alembic/env.py` for async migrations with autogenerate → satisfies US-2.1

---

## Phase 3 — Model, Repository and Migration

> Prerequisite: Phase 2 complete.

- [x] **3.1** Define Python `StrEnum` enums `WeatherEventType` and `NotificationStatus` in `app/models/enums.py` → satisfies US-3.1
- [x] **3.2** Implement `app/models/weather_record.py` (SQLAlchemy model, `event_type` as `VARCHAR(50)`, unique constraint and indexes) → satisfies US-3.1
- [x] **3.3** Implement `app/repositories/base.py` (generic `BaseRepository[T: HasId]` and `SyncBaseRepository[T: HasId]` with Protocol constraint) → satisfies US-2.1
- [x] **3.4** Implement `app/repositories/weather_record_repository.py` (`upsert`, `get_by_zone_event_date_range`) → satisfies US-3.1
- [x] **3.5** Generate Alembic migration `c739caefe40e_initial` (`weather_records` table + constraints + indexes, no native ENUM types) → satisfies US-2.1, US-3.1

---

## Phase 4 — Celery

> Prerequisite: Phase 2 complete.

- [x] **4.1** Implement `app/core/celery_app.py` (Celery app with `task_acks_late`, `task_reject_on_worker_lost`, `worker_prefetch_multiplier=1`, empty beat schedule ready to extend) → satisfies US-5.1

---

## Phase 5 — FastAPI App `[P]`

> Prerequisite: Phases 3 and 4 complete.

- [x] **5.1** `[P]` Implement `app/routers/health.py` (`GET /health` with DB + Redis connectivity check, `HealthResponse` Pydantic model) → satisfies US-6.1
- [x] **5.2** `[P]` Implement `app/scripts/seed_weather.py` (idempotent upsert, 4 zones, 9 event types, 14 days) → satisfies US-4.1
- [x] **5.3** Implement `app/main.py` (FastAPI app factory, register routers, lifespan hook, unhandled exception handler) → satisfies US-1.1

---

## Phase 6 — Docker `[P]`

> Prerequisite: Phase 5 complete.

- [x] **6.1** `[P]` Write `Dockerfile` multi-stage (uv builder + non-root runtime, `--compile-bytecode`, stdlib HEALTHCHECK) → satisfies US-5.1
- [x] **6.2** `[P]` Write `docker-compose.yml` with services: `db`, `redis`, `api`, `worker`, `beat`; healthchecks including `celery inspect ping` for worker → satisfies US-5.1
- [x] **6.3** `[P]` Write `docker-compose.override.yml` for local development (hot reload, volumes) → satisfies US-5.1

---

## Phase 7 — Validation

> Prerequisite: Phase 6 complete.

- [x] **7.1** Run `docker compose up` and verify all services start without errors
- [x] **7.2** Verify migrations run automatically when the `api` container starts
- [x] **7.3** Run the seed script and confirm records in `weather_records` via SQL client
- [x] **7.4** Verify `GET /health` returns `200` with DB and Redis connected
- [x] **7.5** Write `tests/conftest.py` with testcontainers (real Postgres), transaction-rollback isolation per test, and FastAPI DI override
- [x] **7.6** Write `tests/test_weather_records.py` covering upsert idempotency, conflict update, and range query behavior
- [x] **7.7** Configure pre-commit hooks (ruff check + ruff format) and GitHub Actions CI (lint + test jobs)
