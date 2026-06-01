# Requirements — Project Base Setup

## Context

This spec covers the foundation of the Agrobot system: project structure, stack configuration, weather data model, and containerized runtime environment. It represents the state of the system **prior** to the implementation of the climate alerts module.

## User Stories

---

### 1. Project Structure and Configuration

**US-1.1** — As a developer, I want a Python project structured with modern production standards so that the codebase is maintainable and easy to onboard.

**Acceptance Criteria:**
- The project shall define all dependencies and metadata in `pyproject.toml` using `uv` as package manager.
- The project shall separate runtime dependencies from development dependencies.
- The system shall load all configuration from environment variables with typed validation via `pydantic-settings`.
- IF a required environment variable is missing at startup, THEN the system shall fail fast with a descriptive error.
- The project shall include a `.env.example` documenting all required variables with safe placeholder values.

---

### 2. Database and Migrations

**US-2.1** — As a developer, I want an async data access layer with versioned migrations so that schema changes are reproducible across all environments.

**Acceptance Criteria:**
- The system shall expose an async SQLAlchemy engine and session factory for use by FastAPI endpoints.
- The system shall expose a sync SQLAlchemy engine and session factory for use by Celery tasks.
- The system shall manage all schema changes through Alembic migrations.
- WHEN migrations are run against a clean database, the system shall create all tables, indexes, and constraints without errors.
- The system shall use PostgreSQL native UUID generation (`gen_random_uuid()`) as default for all primary keys.
- The system shall use `TIMESTAMPTZ` for all timestamp columns.

---

### 3. Weather Data Model

**US-3.1** — As an ingestion system, I want to persist weather forecast records by zone, date, and event type so that other modules can query them.

**Acceptance Criteria:**
- The system shall store one weather forecast record per `(zone, date, event_type)` combination enforced by a unique constraint.
- The system shall reject any `probability` value outside the range [0.0, 1.0] at the database level.
- WHEN the ingestion job upserts a record that already exists, the system shall update `probability` and `updated_at` without creating a duplicate.
- The system shall index `(zone, date)` to support efficient range lookups by the alert evaluator.

---

### 4. Test Data

**US-4.1** — As a developer, I want an idempotent seed script that generates realistic weather records so I can test the system without depending on the real ingestion job.

**Acceptance Criteria:**
- WHEN the seed script is executed, the system shall insert weather records for at least 4 zones, all 9 event types, and the next 14 days.
- WHEN the seed script is executed more than once, the system shall not create duplicate records (upsert by unique constraint).
- The seed script shall generate probability values that allow alerts to be triggered at typical thresholds (including values >= 0.7).

---

### 5. Containerized Environment

**US-5.1** — As an operator, I want to start the entire system with a single command so I can evaluate and test the project without manual configuration.

**Acceptance Criteria:**
- WHEN `docker compose up` is executed, the system shall start all required services: PostgreSQL, Redis, FastAPI API, Celery Worker, and Celery Beat.
- WHEN the API container starts, the system shall run Alembic migrations automatically before accepting traffic.
- The system shall expose the FastAPI app on a documented port (default: 8000).
- WHEN any service dependency is unavailable, the system shall retry with backoff rather than crash immediately.
- The Dockerfile shall use a multi-stage build to minimize the final image size.
- The project shall include a `docker-compose.override.yml` for local development (hot reload, debug ports).

---

### 6. Base Observability

**US-6.1** — As an operator, I want a health check endpoint and structured logging so I can verify the system state in any environment.

**Acceptance Criteria:**
- The system shall expose a `GET /health` endpoint that returns status 200 when the API and database connection are healthy.
- The system shall emit structured logs (JSON) in production and human-readable logs in development.
- All log entries shall include timestamp, level, service name, and a message.
