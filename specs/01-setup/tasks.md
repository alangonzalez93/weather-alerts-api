# Tasks — Project Base Setup

Each task references the requirements it satisfies. Tasks marked with `[P]` within a phase can be executed in parallel.

---

## Phase 1 — Project Structure and Configuration

- [ ] **1.1** Create project directory structure (`app/`, `tests/`, `alembic/`, `specs/`)
- [ ] **1.2** Create `pyproject.toml` with production and development dependencies, ruff and pytest config → satisfies US-1.1
- [ ] **1.3** Create `.env.example` with all variables documented → satisfies US-1.1
- [ ] **1.4** Implement `app/config.py` with `pydantic-settings` (all variables typed, fail-fast on missing) → satisfies US-1.1
- [ ] **1.5** Configure `structlog` in `app/main.py` (JSON in production, console in development) → satisfies US-6.1

---

## Phase 2 — Database `[P]`

> Prerequisite: Phase 1 complete.

- [ ] **2.1** `[P]` Implement `app/database.py` (async engine + `AsyncSession` factory, `get_async_session` dependency) → satisfies US-2.1
- [ ] **2.2** `[P]` Implement `app/database_sync.py` (sync engine + `Session` factory, `get_sync_session` context manager) → satisfies US-2.1
- [ ] **2.3** Initialize Alembic (`alembic init`) and configure `alembic/env.py` for async migrations with autogenerate → satisfies US-2.1

---

## Phase 3 — Model, Repository and Migration

> Prerequisite: Phase 2 complete.

- [ ] **3.1** Define Python `str` enums `WeatherEventType` and `NotificationStatus` in `app/models/__init__.py` → satisfies US-3.1
- [ ] **3.2** Implement `app/models/weather_record.py` (SQLAlchemy model, `event_type` as `VARCHAR(50)`, unique constraint and indexes) → satisfies US-3.1
- [ ] **3.3** Implement `app/repositories/base.py` (generic `BaseRepository[T]` with `get_by_id`, `create`, `update`, `delete`) → satisfies US-2.1
- [ ] **3.4** Implement `app/repositories/weather_record_repository.py` (`upsert`, `get_by_zone_event_date_range`) → satisfies US-3.1
- [ ] **3.5** Generate Alembic migration `0001_initial` (`weather_records` table + constraints + indexes, no native ENUM types) → satisfies US-2.1, US-3.1

---

## Phase 4 — Celery

> Prerequisite: Phase 2 complete.

- [ ] **4.1** Implement `app/celery_app.py` (Celery app configured with Redis broker and empty beat schedule ready to extend) → satisfies US-5.1

---

## Phase 5 — FastAPI App `[P]`

> Prerequisite: Phases 3 and 4 complete.

- [ ] **5.1** `[P]` Implement `app/routers/health.py` (`GET /health` with DB connectivity check) → satisfies US-6.1
- [ ] **5.2** `[P]` Implement `app/scripts/seed_weather.py` (idempotent upsert, 4 zones, 9 event types, 14 days) → satisfies US-4.1
- [ ] **5.3** Implement `app/main.py` (FastAPI app factory, register routers, lifespan hook) → satisfies US-1.1

---

## Phase 6 — Docker `[P]`

> Prerequisite: Phase 5 complete.

- [ ] **6.1** `[P]` Write `Dockerfile` multi-stage (uv builder + non-root runtime) → satisfies US-5.1
- [ ] **6.2** `[P]` Write `docker-compose.yml` with services: `db`, `redis`, `api`, `worker`, `beat` and healthchecks → satisfies US-5.1
- [ ] **6.3** `[P]` Write `docker-compose.override.yml` for local development (hot reload, volumes) → satisfies US-5.1

---

## Phase 7 — Validation

> Prerequisite: Phase 6 complete.

- [ ] **7.1** Run `docker compose up` and verify all services start without errors
- [ ] **7.2** Verify migrations run automatically when the `api` container starts
- [ ] **7.3** Run the seed script and confirm records in `weather_records` via `psql` or SQL client
- [ ] **7.4** Verify `GET /health` returns `200` with DB connected
- [ ] **7.5** Write `tests/conftest.py` with base fixtures (async test client, test DB session)
