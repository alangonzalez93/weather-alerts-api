# Design — Alerts Module

## Stack

Same as `01-setup`, plus one direct dependency:

| Package   | Reason |
|-----------|--------|
| `redis`   | Distributed lock in `evaluate_alerts` (`redis.from_url`, `SET NX EX`). Already a transitive dep of Celery but must be declared explicitly to pin the version. |

---

## Data Model

### AuditMixin — Base for all models

All tables inherit from `AuditMixin` (defined in `app/models/base_model.py`). The following four columns are present on every table and are not repeated in the per-table specs below:

| Column       | Type        | Constraints                   |
|--------------|-------------|-------------------------------|
| `id`         | UUID        | PK, default gen_random_uuid() |
| `deleted`    | BOOLEAN     | NOT NULL, default false       |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now()       |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now()       |

**Soft delete behavior:**
- Records are never physically deleted from the database.
- `DELETE` operations set `deleted=True` and `updated_at=now()`.
- `BaseRepository` applies `deleted=False` automatically on **every query** — `get_by_id`, `list`, and all custom methods. Concrete repositories never need to add this filter explicitly; it is enforced once in the base class.
- **Bulk soft-delete**: operations that affect multiple rows at once (e.g. `soft_delete_pending_by_alert`) MUST use a SQLAlchemy Core `update()` statement — never ORM row-by-row iteration. This guarantees a single SQL round-trip regardless of row count.
- The `AuditMixin` exposes a `not_deleted()` classmethod that returns the standard filter clause so the base repository can reference it without hardcoding column names:
  ```python
  @classmethod
  def not_deleted(cls) -> ColumnElement[bool]:
      return cls.deleted == False
  ```

### Enums (Python `StrEnum`, stored as `VARCHAR` — no PostgreSQL native enums)

`WeatherEventType` and `NotificationStatus` are already defined in `app/models/enums.py` from the setup phase.

New enum added in this phase:

```python
class NotificationChannel(enum.StrEnum):
    whatsapp = "whatsapp"
    email    = "email"
```

---

### `weather_forecasts` (existing — read-only by this module)

Defined in `01-setup`. The evaluator queries this table but never writes to it. Inherits `id`, `deleted`, `created_at`, `updated_at` from `AuditMixin`.

| Column        | Type         | Constraints                       |
|---------------|--------------|-----------------------------------|
| `zone`        | VARCHAR(100) | NOT NULL                          |
| `date`        | DATE         | NOT NULL                          |
| `event_type`  | VARCHAR(50)  | NOT NULL                          |
| `probability` | FLOAT        | NOT NULL, CHECK (0.0 <= x <= 1.0) |

**Index:** `(zone, event_type, date)` — evaluator query pattern

---

### `alerts`

Inherits `id`, `deleted`, `created_at`, `updated_at` from `AuditMixin`.

| Column                 | Type         | Constraints                       |
|------------------------|--------------|-----------------------------------|
| `field_id`             | UUID         | NOT NULL                          |
| `zone`                 | VARCHAR(100) | NOT NULL                          |
| `event_type`           | VARCHAR(50)  | NOT NULL                          |
| `threshold`            | FLOAT        | NOT NULL, CHECK (0.0 <= x <= 1.0) |
| `is_active`            | BOOLEAN      | NOT NULL, default TRUE            |
| `notification_channel` | VARCHAR(20)  | NOT NULL                          |
| `contact`              | VARCHAR(255) | NOT NULL                          |

> `field_id` is a logical reference to the client's field. No `fields` table exists — no FK constraint. Cross-service references use UUIDs directly (see `01-setup` design for rationale).

> `contact` holds the destination address: E.164 phone number for `whatsapp` (e.g. `+5491112345678`), email address for `email`. Validated at the API layer via a Pydantic cross-field validator — not enforced at the DB level.

**Indexes:**
- `(field_id, is_active, created_at DESC)` — API list query: filters by field + active status and supports ordered result in one B-tree pass
- `(is_active, id) WHERE deleted = false` — evaluator cursor scan: forward traversal over active non-deleted alerts ordered by id (partial index eliminates deleted rows)
- `(zone, event_type)` — evaluator forecast lookup pattern

---

### `notifications`

Inherits `id`, `deleted`, `created_at`, `updated_at` from `AuditMixin`.

> Notifications are **write-once** from a business logic perspective — once created they are not modified by users. The evaluator updates `status` (pending → sent/failed), which is reflected in `updated_at`.

> Multiple notifications can exist for the same `(alert_id, target_date)` — no unique constraint. The evaluator checks only the most recent one (`ORDER BY triggered_at DESC LIMIT 1`) to decide whether to re-notify.

> `ON DELETE RESTRICT` on the FK is intentional. The app exclusively soft-deletes alerts; a physical DELETE should never happen and must error loudly rather than cascade-wipe historical notification records silently.

| Column         | Type        | Constraints                                   |
|----------------|-------------|-----------------------------------------------|
| `alert_id`     | UUID        | NOT NULL, FK → alerts(id) ON DELETE RESTRICT  |
| `target_date`  | DATE        | NOT NULL                                      |
| `probability`  | FLOAT       | NOT NULL                                      |
| `status`       | VARCHAR(20) | NOT NULL, default 'pending'                   |
| `triggered_at` | TIMESTAMPTZ | NOT NULL, default now()                       |

**Indexes:**
- `(alert_id, target_date)` — evaluator deduplication lookup
- `(alert_id, status) WHERE deleted = false` — API list filtering + `soft_delete_pending_by_alert` bulk update
- `(status, id) WHERE deleted = false` — evaluator Phase 2 cursor scan over pending notifications

---

## Project Structure (additions to `01-setup`)

```
app/
├── models/
│   ├── alert.py                          # Alert ORM model
│   └── notification.py                   # Notification ORM model
├── repositories/
│   ├── alert_repository.py               # Async (FastAPI)
│   ├── notification_repository.py        # Async (FastAPI)
│   ├── alert_sync_repository.py          # Sync (Celery worker)
│   ├── notification_sync_repository.py   # Sync (Celery worker)
│   └── weather_forecast_sync_repository.py  # Sync (Celery worker — evaluator reads forecasts)
├── schemas/
│   ├── alert.py                     # AlertCreate, AlertUpdate, AlertResponse
│   ├── notification.py              # NotificationResponse
│   └── common.py                    # PaginatedResponse[T]
├── services/
│   ├── alert_service.py             # CRUD orchestration
│   └── notification_service.py      # List with filters
├── routers/
│   ├── alerts.py                    # POST/GET/PATCH/DELETE /api/v1/alerts
│   └── notifications.py             # GET /api/v1/alerts/{id}/notifications
├── core/
│   └── redis_client.py              # Shared Redis client — redis.from_url(settings.redis_url)
└── tasks/
    ├── evaluate_alerts.py           # Celery periodic task — creates pending notifications
    └── deliver_notification.py      # Celery task — delivers one notification, retries on failure
```

---

## REST API

Base path: `/api/v1`

Error response shape:
```json
{ "detail": "descriptive message" }
```

### Alerts

#### `POST /api/v1/alerts`
```
Request  → AlertCreate { field_id: UUID, zone: str, event_type: WeatherEventType, threshold: float, notification_channel: NotificationChannel, contact: str }
Response → 201 AlertResponse | 422 ValidationError
```

#### `GET /api/v1/alerts`
```
Query    → field_id: UUID (required), is_active?: bool, limit?: int = 50 (max 200), offset?: int = 0
Response → 200 PaginatedResponse[AlertResponse]  (ordered by created_at DESC)
```

#### `GET /api/v1/alerts/{alert_id}`
```
Response → 200 AlertResponse | 404
```

#### `PATCH /api/v1/alerts/{alert_id}`
```
Request  → AlertUpdate { threshold?: float, is_active?: bool, contact?: str, notification_channel?: NotificationChannel }
Response → 200 AlertResponse | 404 | 422
```

> `AlertUpdate` allows updating `contact` and `notification_channel` together. If either is provided, both must be re-validated as a pair (same cross-field rule as `AlertCreate`).

#### `DELETE /api/v1/alerts/{alert_id}`
```
Response → 204 | 404
```

### Notifications

#### `GET /api/v1/alerts/{alert_id}/notifications`
```
Query    → status?: NotificationStatus, from_date?: date, to_date?: date, limit?: int = 50 (max 200), offset?: int = 0
Response → 200 PaginatedResponse[NotificationResponse] (ordered by triggered_at DESC)
```

---

## Pydantic Schemas

```python
# PaginatedResponse — generic envelope for all paginated list endpoints
# Python 3.12 type parameter syntax (PEP 695) — no TypeVar or Generic import needed
class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int

# AlertCreate — request body for POST
class AlertCreate(BaseModel):
    field_id: UUID
    zone: str = Field(min_length=1, max_length=100)
    event_type: WeatherEventType
    threshold: float = Field(ge=0.0, le=1.0)
    notification_channel: NotificationChannel
    contact: str = Field(min_length=1, max_length=255)


    @model_validator(mode="after")
    def validate_contact_format(self) -> "AlertCreate":
        if self.notification_channel == NotificationChannel.whatsapp:
            # E.164 format: + followed by 7-15 digits
            if not re.match(r"^\+\d{7,15}$", self.contact):
                raise ValueError("contact must be a valid E.164 phone number (e.g. +5491112345678)")
        elif self.notification_channel == NotificationChannel.email:
            if "@" not in self.contact or "." not in self.contact.split("@")[-1]:
                raise ValueError("contact must be a valid email address")
        return self

# AlertUpdate — request body for PATCH (all fields optional)
class AlertUpdate(BaseModel):
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool | None = None
    contact: str | None = Field(default=None, min_length=1, max_length=255)
    notification_channel: NotificationChannel | None = None

    @model_validator(mode="after")
    def validate_contact_format(self) -> "AlertUpdate":
        if self.notification_channel is not None or self.contact is not None:
            if self.notification_channel is None or self.contact is None:
                raise ValueError("contact and notification_channel must both be provided together")
            if self.notification_channel == NotificationChannel.whatsapp:
                if not re.match(r"^\+\d{7,15}$", self.contact):
                    raise ValueError("contact must be a valid E.164 phone number (e.g. +5491112345678)")
            elif self.notification_channel == NotificationChannel.email:
                if "@" not in self.contact or "." not in self.contact.split("@")[-1]:
                    raise ValueError("contact must be a valid email address")
        return self

# AlertResponse — response for all alert endpoints
class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    field_id: UUID
    zone: str
    event_type: WeatherEventType
    threshold: float
    is_active: bool
    notification_channel: NotificationChannel
    contact: str
    created_at: datetime
    updated_at: datetime

# NotificationResponse — response for notification endpoints
class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    alert_id: UUID
    target_date: date
    probability: float
    status: NotificationStatus
    triggered_at: datetime
```

---

## Background Job — Alert Evaluator

### Celery Architecture

```
┌─────────────┐     HTTP      ┌─────────────┐
│  FastAPI    │ ◄───────────► │  PostgreSQL │
│  (async)    │               └─────────────┘
└─────────────┘                      ▲
                                     │ sync queries
┌─────────────┐   enqueue   ┌────────┴────┐
│ Celery Beat │ ──────────► │   Redis     │
│ (scheduler) │             │  (broker)   │
└─────────────┘             └──────┬──────┘
                                   │ consume
                            ┌──────▼──────┐     ┌─────────────┐
                            │   Celery    │────►│  PostgreSQL │
                            │   Worker    │     └─────────────┘
                            └─────────────┘
```

FastAPI uses `AsyncSession`. The Celery worker uses `Session` (sync) via `get_sync_session()` — both engines are already configured in `app/core/database.py` and `app/core/database_sync.py`.

### Task Architecture

Two Celery tasks with clearly separated responsibilities:

```
Celery Beat
    │
    ▼ every ALERT_EVAL_INTERVAL_SECONDS
┌─────────────────────┐
│   evaluate_alerts   │  periodic — evaluates all active alerts,
│   (batched, sync)   │  creates Notification rows (status=pending),
└────────┬────────────┘  enqueues one deliver_notification task per row
         │ .delay(notification_id) × N
         ▼
      Redis queue
         │
         ▼ consumed by workers
┌──────────────────────────┐
│  deliver_notification    │  one task per notification — its own
│  (one per notif, sync)   │  transaction, Celery retry on failure
└──────────────────────────┘  (max 3x, exponential backoff + jitter, task_acks_late)
```

**Why this pattern**: each `deliver_notification` task runs in its own Celery execution context with its own transaction. `task_acks_late=True` (configured globally) guarantees that if a worker crashes mid-delivery, Redis re-queues the task and another worker retries it. No polling loops or manual retry logic needed.

### Evaluator Algorithm

```python
# ── evaluate_alerts.py ────────────────────────────────────────────────────────

EVAL_LOCK_KEY = "lock:evaluate_alerts"

@celery_app.task(name="evaluate_alerts")
def evaluate_alerts() -> None:
    # Distributed lock — prevents concurrent runs if a cycle outlasts the interval.
    # TTL = 2 × ALERT_EVAL_INTERVAL_SECONDS so stale locks from crashed workers
    # expire before the second scheduled firing.
    lock_ttl = settings.alert_eval_interval_seconds * 2
    acquired = redis_client.set(EVAL_LOCK_KEY, "1", nx=True, ex=lock_ttl)
    if not acquired:
        logger.warning("[EVALUATOR] skipping cycle — already running", extra={"lock_key": EVAL_LOCK_KEY})
        return

    try:
        _run_evaluation()
    finally:
        redis_client.delete(EVAL_LOCK_KEY)


def _run_evaluation() -> None:
    today = datetime.now(tz=UTC).date()
    lookahead = today + timedelta(days=settings.alert_lookahead_days)
    batch_size = settings.alert_eval_batch_size  # default: 500

    # ── Phase 1: evaluate alerts, create pending notifications ─────────────────
    # Cursor-based pagination (after_id) instead of OFFSET:
    #   - OFFSET N forces PostgreSQL to scan and discard N rows — O(N) cost.
    #   - Cursor is O(1): WHERE id > :last_id on the (is_active, id) index.
    #   - No drift: new alerts created mid-cycle are never missed or double-counted.
    after_id: UUID | None = None
    while True:
        with get_sync_session() as session:
            alert_repo = AlertSyncRepository(session)
            forecast_repo = WeatherForecastSyncRepository(session)
            notification_repo = NotificationSyncRepository(session)

            batch = alert_repo.get_active(limit=batch_size, after_id=after_id)
            if not batch:
                break

            # Pre-fetch forecasts for all unique (zone, event_type) pairs in the batch.
            # Avoids N redundant DB queries when many alerts share the same zone/event.
            zone_event_pairs = {(a.zone, a.event_type) for a in batch}
            forecast_cache: dict[tuple, list] = {
                (zone, event_type): forecast_repo.get_by_zone_event_date_range(
                    zone=zone, event_type=event_type, date_from=today, date_to=lookahead,
                )
                for zone, event_type in zone_event_pairs
            }

            for alert in batch:
                try:
                    _evaluate_alert(alert, forecast_cache[(alert.zone, alert.event_type)], notification_repo, today, lookahead)
                except Exception:
                    logger.exception("[EVALUATOR] alert processing failed", extra={"alert_id": str(alert.id)})

            after_id = batch[-1].id

    # ── Phase 2: enqueue ALL pending notifications from DB ─────────────────────
    # Cursor-based for same reasons as Phase 1.
    # Picks up notifications stuck in pending from previous failed runs — self-healing.
    after_id = None
    total_enqueued = 0
    while True:
        with get_sync_session() as session:
            notification_repo = NotificationSyncRepository(session)
            pending = notification_repo.get_pending(limit=batch_size, after_id=after_id)
            if not pending:
                break
            for notification in pending:
                deliver_notification.delay(str(notification.id))
                total_enqueued += 1
            after_id = pending[-1].id

    logger.info(
        "[EVALUATOR] Cycle complete",
        extra={"enqueued": total_enqueued, "batch_size": batch_size},
    )


def _evaluate_alert(alert, forecasts, notification_repo, date_from, date_to) -> None:
    # One query fetches the latest notification for every date in the lookahead window.
    # Avoids up to 7 per-date queries per alert — result is consumed from memory below.
    latest_by_date = notification_repo.get_latest_by_dates_for_alert(alert.id, date_from, date_to)

    for forecast in forecasts:
        if forecast.probability < alert.threshold:
            continue

        last = latest_by_date.get(forecast.date)

        should_notify = last is None or (
            abs(forecast.probability - last.probability) >= settings.alert_renotify_delta
        )

        if should_notify:
            notification_repo.create(Notification(
                alert_id=alert.id,
                target_date=forecast.date,
                probability=forecast.probability,
            ))


# ── deliver_notification.py ───────────────────────────────────────────────────

@celery_app.task(
    name="deliver_notification",
    bind=True,
    max_retries=3,
)
def deliver_notification(self, notification_id: str) -> None:
    with get_sync_session() as session:
        notification_repo = NotificationSyncRepository(session)
        notification = notification_repo.get_by_id(UUID(notification_id))

        if notification is None or notification.status != NotificationStatus.pending:
            return  # already delivered or soft-deleted — idempotent skip

        alert_repo = AlertSyncRepository(session)
        alert = alert_repo.get_by_id(notification.alert_id)
        if alert is None:
            return  # alert was soft-deleted after notification was created

        try:
            _deliver(notification, alert)
            notification_repo.update_status(notification, NotificationStatus.sent)
        except Exception as exc:
            # Exponential backoff with jitter: 60s, ~120s, ~240s.
            # Jitter prevents thundering herds when many notifications fail simultaneously.
            delay = 60 * (2 ** self.request.retries) + random.uniform(0, 30)
            try:
                raise self.retry(exc=exc, countdown=delay)
            except MaxRetriesExceededError:
                notification_repo.update_status(notification, NotificationStatus.failed)
                logger.exception(
                    "[DELIVERY] max retries exceeded",
                    extra={"notification_id": notification_id},
                )


def _build_message(notification, alert) -> str:
    pct = round(notification.probability * 100)
    event = alert.event_type.replace("_", " ")
    return (
        f"Weather alert for zone '{alert.zone}': {event} forecast on {notification.target_date} "
        f"with {pct}% probability — exceeds your configured threshold of "
        f"{round(alert.threshold * 100)}%. Take the necessary precautions."
    )


def _deliver(notification, alert) -> None:
    # Logs the notification — replace with real channel dispatch when integrating.
    # Message is built once and included both in the human-readable log string
    # and in the structured extra dict for log aggregation.
    message = _build_message(notification, alert)
    channel = alert.notification_channel

    if channel == "whatsapp":
        logger.info(
            "[DELIVERY] WhatsApp → %s | alert=%s | %s",
            alert.contact, notification.alert_id, message,
            extra={"channel": channel, "contact": alert.contact,
                   "alert_id": str(notification.alert_id),
                   "target_date": str(notification.target_date),
                   "probability": notification.probability},
        )
    elif channel == "email":
        logger.info(
            "[DELIVERY] Email → %s | alert=%s | %s",
            alert.contact, notification.alert_id, message,
            extra={"channel": channel, "contact": alert.contact,
                   "alert_id": str(notification.alert_id),
                   "target_date": str(notification.target_date),
                   "probability": notification.probability},
        )
```

### Celery Beat Schedule

```python
# Registered in app/core/celery_app.py during app startup
# Only evaluate_alerts is periodic — deliver_notification is enqueued on demand
celery_app.conf.beat_schedule = {
    "evaluate-alerts": {
        "task": "evaluate_alerts",
        "schedule": settings.alert_eval_interval_seconds,
    }
}
```

### Scale Considerations

- **Distributed lock**: `evaluate_alerts` acquires a Redis `SET NX EX` lock at startup. Concurrent firings (e.g. when a cycle outlasts `ALERT_EVAL_INTERVAL_SECONDS`) are detected immediately and exit without doing any work. Lock TTL = 2 × interval so stale locks from crashed workers auto-expire.
- **Cursor-based evaluation**: `get_active(limit, after_id)` and `get_pending(limit, after_id)` use `WHERE id > :last_id` cursor pagination instead of `OFFSET`. `OFFSET N` scans and discards N rows — O(N) cost that degrades linearly with table size. Cursor pagination is O(1) on the `(is_active, id)` index.
- **Forecast pre-fetch per batch**: before evaluating individual alerts, all unique `(zone, event_type)` pairs in the batch are fetched in bulk and cached in a dict. Eliminates N redundant DB queries when many alerts share the same zone/event combination.
- **Batch size default=500**: processes 100k active alerts in ~200 DB round-trips instead of ~1,000 at the old default of 100.
- **Delivery via Celery tasks**: after all evaluation batches commit, `evaluate_alerts` queries ALL `pending` notifications from DB and enqueues one `deliver_notification` task per row. Enqueuing happens only after DB commit — nothing in Redis that isn't already persisted.
- **Self-healing**: if the worker crashed between DB commit and Redis enqueue in a previous run, those notifications remain `pending`. The next run of `evaluate_alerts` picks them up in the Phase 2 query and re-enqueues them automatically.
- **Idempotency in delivery**: `deliver_notification` checks `status == pending` before delivering — if the same notification is enqueued twice, the second execution is a no-op.
- **Idempotency in evaluation**: re-running `evaluate_alerts` never creates duplicate notifications — the `get_latest_by_dates_for_alert` check guarantees this.
- **Separate pool sizing for API vs workers**: the API and Celery workers have different connection needs. The API handles concurrent async requests — a larger pool makes sense. Each Celery worker processes one task at a time (`prefetch=1`) and holds at most one connection per task. Giving workers the same `pool_size=10` as the API wastes 9 idle connections per worker. Settings provide separate values: `DB_POOL_SIZE/DB_MAX_OVERFLOW` for the async engine (API), `DB_WORKER_POOL_SIZE/DB_WORKER_MAX_OVERFLOW` for the sync engine (workers). Formula to stay within Postgres `max_connections`: `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × api_processes + (DB_WORKER_POOL_SIZE + DB_WORKER_MAX_OVERFLOW) × num_workers ≤ max_connections - superuser_reserved`. With defaults (10+20)×1 + (2+3)×8 = 70 — within the Postgres default of 100.
- **Table growth — `notifications`**: at 100k active alerts × 7-day lookahead × daily evaluation cycles the table grows by ~700k rows/week. Recommended mitigation: PostgreSQL range partitioning by `triggered_at` (monthly partitions) + a periodic archiving job that moves records older than 90 days with `status IN ('sent', 'failed')` to a cold-storage partition.
- **Structured logging**: all evaluator and delivery log entries MUST use `logger.info/exception(..., extra={...})` with a consistent set of keys (`alert_id`, `notification_id`, `enqueued`, `channel`, etc.) so log aggregation (Datadog, CloudWatch, etc.) can build metrics without parsing free-form strings.
