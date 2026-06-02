# Tasks — Alerts Module

Each task references the requirements it satisfies. Tasks marked with `[P]` within a phase can be executed in parallel.

> Prerequisite: `01-setup` phase fully complete — database, async/sync sessions, Celery infrastructure, and `weather_forecasts` table are already in place.

---

## Phase 0 — Extend 01-setup Artifacts

These tasks update existing `01-setup` code to support the `AuditMixin` pattern introduced in this phase. They must be done before any new models are created.

- [ ] **0.1** Implement `app/models/base_model.py` with `AuditMixin` class — `id`, `deleted`, `created_at`, `updated_at` columns
- [ ] **0.2** Refactor `app/models/weather_forecast.py` to inherit from `AuditMixin` — remove `id`, `created_at`, `updated_at` from the model (now provided by mixin)
- [ ] **0.3** Update `app/repositories/base.py`:
  - Replace `HasId` Protocol with `AuditFields` (adds `deleted: bool` and `updated_at: datetime`)
  - Update `get_by_id()` to filter `deleted=False`
  - Update `delete()` to set `deleted=True` and `updated_at=now()` instead of physically deleting
  - Apply same changes to `SyncBaseRepository`
- [ ] **0.4** Rebuild DB locally to pick up `AuditMixin` changes: `docker compose down -v && docker compose up -d`
- [ ] **0.5** Add `NotificationChannel` enum to `app/models/enums.py`
- [ ] **0.6** Add `redis` to project dependencies (`pyproject.toml` / `requirements.txt`) and implement `app/core/redis_client.py`:
  ```python
  import redis
  from app.core.config import settings
  redis_client = redis.from_url(settings.redis_url, decode_responses=True)
  ```
  `evaluate_alerts.py` imports `redis_client` from this module.

---

## Phase 1 — Models and Migration `[P]`

- [ ] **1.1** `[P]` Implement `app/models/alert.py` — inherits `AuditMixin`, `field_id` as logical UUID reference, `notification_channel` + `contact` columns, indexes → satisfies US-1.1
- [ ] **1.2** `[P]` Implement `app/models/notification.py` — inherits `AuditMixin`, FK to alerts with `ON DELETE RESTRICT` (not CASCADE — app exclusively soft-deletes), indexes → satisfies US-2.1
- [ ] **1.3** Register `Alert` and `Notification` in `app/models/__init__.py` so Alembic autogenerate detects them
- [ ] **1.4** Generate a single Alembic migration covering all schema changes in this phase:
  - Add `deleted BOOLEAN NOT NULL DEFAULT false` to `weather_forecasts`
  - Create `alerts` table with all columns, constraints, and indexes
  - Create `notifications` table with FK to `alerts`, constraints, and indexes
  - **Partial indexes must be written manually** — Alembic autogenerate silently drops the `WHERE` clause. After running `alembic revision --autogenerate`, hand-edit the migration to add `postgresql_where=sa.text('deleted = false')` to the three partial indexes:
    ```python
    # alerts
    op.create_index('ix_alerts_is_active_id', 'alerts', ['is_active', 'id'],
                    postgresql_where=sa.text('deleted = false'))
    # notifications
    op.create_index('ix_notifications_alert_id_status', 'notifications', ['alert_id', 'status'],
                    postgresql_where=sa.text('deleted = false'))
    op.create_index('ix_notifications_status_id', 'notifications', ['status', 'id'],
                    postgresql_where=sa.text('deleted = false'))
    ```

---

## Phase 2 — Repositories `[P]`

> Prerequisite: Phase 1 complete.

- [ ] **2.1** `[P]` Implement `app/repositories/alert_repository.py` — async, extends `BaseRepository[Alert]`:
  - `get_by_id`, `create`, `update`, `delete` (inherited — all filter `deleted=False` automatically via base)
  - `list(field_id: UUID, is_active?, limit, offset) → tuple[list[Alert], int]` — `field_id` is required; returns (rows, total_count) for paginated envelope; ordered by `created_at DESC`
- [ ] **2.2** `[P]` Implement `app/repositories/notification_repository.py` — async, extends `BaseRepository[Notification]`:
  - `list_by_alert(alert_id, status?, from_date?, to_date?, limit, offset) → tuple[list[Notification], int]` — returns (rows, total_count); ordered by `triggered_at DESC`
  - `soft_delete_pending_by_alert(alert_id)` — single SQLAlchemy Core `update()` statement (NOT ORM row iteration); sets `deleted=True, updated_at=now()` for all pending non-deleted rows matching `alert_id`
- [ ] **2.3** `[P]` Implement `app/repositories/alert_sync_repository.py` — sync, extends `SyncBaseRepository[Alert]`:
  - `get_active(limit: int, after_id: UUID | None) → list[Alert]` — cursor-based fetch: `WHERE is_active=true AND deleted=false AND id > :after_id ORDER BY id ASC`; `after_id=None` starts from the beginning
- [ ] **2.4** `[P]` Implement `app/repositories/notification_sync_repository.py` — sync, extends `SyncBaseRepository[Notification]`:
  - `get_latest_by_dates_for_alert(alert_id, date_from, date_to) → dict[date, Notification | None]` — single query returning the most recent non-deleted notification per date in the lookahead window; used by `_evaluate_alert` to avoid N per-date queries (`DISTINCT ON (target_date)` ordered by `triggered_at DESC`)
  - `get_pending(limit, after_id: UUID | None) → list[Notification]` — cursor-based fetch: `WHERE status='pending' AND deleted=false AND id > :after_id ORDER BY id ASC`
  - `update_status(notification, status)` — ORM-level update (single row — idiomatic for single-record state transitions)
- [ ] **2.5** `[P]` Implement `app/repositories/weather_forecast_sync_repository.py` — sync, extends `SyncBaseRepository[WeatherForecast]`:
  - `get_by_zone_event_date_range(zone, event_type, date_from, date_to)` — evaluator forecast lookup

---

## Phase 3 — Schemas `[P]`

> Prerequisite: Phase 1 complete.

- [ ] **3.1** `[P]` Implement `app/schemas/alert.py`:
  - `AlertCreate` — `field_id`, `zone`, `event_type`, `threshold` (ge=0.0, le=1.0), `notification_channel`, `contact`
  - `AlertCreate` must include a `@model_validator` that validates `contact` format against `notification_channel` (E.164 for whatsapp, email format for email)
  - `AlertUpdate` — all fields optional; `contact` and `notification_channel` must be provided together and re-validated as a pair (same cross-field rule as `AlertCreate`)
  - `AlertResponse` — full model including `notification_channel` and `contact`, `model_config = ConfigDict(from_attributes=True)`
- [ ] **3.2** `[P]` Implement `app/schemas/notification.py`:
  - `NotificationResponse` — `id`, `alert_id`, `target_date`, `probability`, `status`, `triggered_at`
- [ ] **3.3** Implement `app/schemas/common.py`:
  - `PaginatedResponse[T]` — generic envelope with `items: list[T]`, `total: int`, `limit: int`, `offset: int`
  - All list endpoints MUST return this type; limit query param capped at `le=200`

---

## Phase 4 — Services `[P]`

> Prerequisite: Phases 2 and 3 complete.

- [ ] **4.1** `[P]` Implement `app/services/alert_service.py` — orchestrates repository calls:
  - `create(data: AlertCreate, session) → Alert` → satisfies US-1.1
  - `get(alert_id, session) → Alert` (raises 404 if not found or deleted) → satisfies US-1.1
  - `list(field_id: UUID, is_active?, limit, offset, session) → tuple[list[Alert], int]` → satisfies US-1.1
  - `update(alert_id, data: AlertUpdate, session) → Alert` (raises 404 if not found or deleted) → satisfies US-1.2
  - `delete(alert_id, session) → None`:
    1. Raises 404 if alert not found or already deleted
    2. Calls `notification_repo.soft_delete_pending_by_alert(alert_id)` to soft-delete pending notifications
    3. Soft-deletes the alert itself via `alert_repo.delete(alert)`
    > Steps 2 and 3 use the same `session` — they execute in the same transaction and commit together. Never instantiate separate sessions for these two operations.
    → satisfies US-1.3
- [ ] **4.2** `[P]` Implement `app/services/notification_service.py`:
  - `list(alert_id, status?, from_date?, to_date?, limit, offset, session) → tuple[list[Notification], int]`:
    1. Calls `alert_repo.get_by_id(alert_id)` — raises 404 if alert not found or deleted
    2. Calls `notification_repo.list_by_alert(...)` and returns the paginated result
    → satisfies US-2.1

---

## Phase 5 — Routers `[P]`

> Prerequisite: Phase 4 complete.

- [ ] **5.1** `[P]` Implement `app/routers/alerts.py` with prefix `/api/v1/alerts`:
  - `POST /` → AlertCreate → 201 AlertResponse → satisfies US-1.1
  - `GET /` → `field_id: UUID` (required), `is_active?`, `limit: int = Query(50, ge=1, le=200)`, `offset: int = Query(0, ge=0)` → 200 PaginatedResponse[AlertResponse] | 422 → satisfies US-1.1
  - `GET /{alert_id}` → 200 AlertResponse | 404 → satisfies US-1.1
  - `PATCH /{alert_id}` → AlertUpdate → 200 AlertResponse | 404 | 422 → satisfies US-1.2
  - `DELETE /{alert_id}` → 204 | 404 → satisfies US-1.3
- [ ] **5.2** `[P]` Implement `app/routers/notifications.py` with prefix `/api/v1/alerts`:
  - `GET /{alert_id}/notifications` → `status?`, `from_date?`, `to_date?`, `limit: int = Query(50, ge=1, le=200)`, `offset: int = Query(0, ge=0)` → 200 PaginatedResponse[NotificationResponse] → satisfies US-2.1
- [ ] **5.3** Register both routers in `app/main.py` with prefix `/api/v1`

---

## Phase 6 — Background Job

> Prerequisite: Phase 2 complete.

- [ ] **6.1** Implement `app/tasks/evaluate_alerts.py` → satisfies US-3.1:
  - `evaluate_alerts()` — acquires Redis distributed lock (`SET NX EX`) before doing any work; exits immediately if lock already held; releases lock in `finally`
  - `_run_evaluation()` — cursor-based batched loop (Phase 1 + Phase 2), one transaction per batch
  - Phase 1: pre-fetches forecasts per unique `(zone, event_type)` pair in each batch (forecast cache dict) before iterating individual alerts
  - `_evaluate_alert(alert, forecasts, notification_repo, date_from, date_to) → None` — fetches latest notifications for the full window in one query (`get_latest_by_dates_for_alert`), then evaluates each forecast against the in-memory result; creates notifications directly, no return value
  - Phase 2: cursor-based loop over `pending` notifications; enqueues `deliver_notification.delay(id)` for each
  - Logs structured end-of-cycle summary: `enqueued` count
- [ ] **6.2** Implement `app/tasks/deliver_notification.py` → satisfies US-3.1:
  - `deliver_notification(notification_id)` — `bind=True`, `max_retries=3` (no `default_retry_delay` — delay is computed per-retry)
  - Checks `status == pending` before delivering (idempotent)
  - On success: `update_status(sent)`
  - On failure: `self.retry(exc=exc, countdown=60 * (2 ** self.request.retries) + random.uniform(0, 30))` — exponential backoff with jitter
  - On retry exhausted: `update_status(failed)` + structured log
  - `_deliver(notification, alert)` — logs the notification (WhatsApp/email integration placeholder)
- [ ] **6.3** Register `evaluate_alerts` in `app/core/celery_app.py` beat schedule using `settings.alert_eval_interval_seconds`
- [ ] **6.4** Update `app/core/celery_app.py` `include` to list both task modules explicitly:
  `["app.tasks.evaluate_alerts", "app.tasks.deliver_notification"]`

---

## Phase 7 — Validation and Tests

> Prerequisite: Phases 5 and 6 complete.

- [ ] **7.1** Verify migrations run cleanly against local PostgreSQL
- [ ] **7.2** Run seed script and confirm evaluator creates notifications end-to-end (Docker Compose)
- [ ] **7.3** `[P]` Write integration tests for alert endpoints → satisfies US-1.1, US-1.2, US-1.3:
  - `test_create_alert` — 201, response shape
  - `test_create_alert_invalid_threshold` — 422
  - `test_create_alert_invalid_event_type` — 422
  - `test_create_alert_whatsapp_invalid_phone` — 422
  - `test_create_alert_email_invalid_format` — 422
  - `test_get_alert_not_found` — 404
  - `test_list_alerts_requires_field_id` — omitting `field_id` returns 422
  - `test_list_alerts_filtered_by_field_id`
  - `test_list_alerts_filtered_by_is_active`
  - `test_list_alerts_pagination` — verifies `offset` skips correct rows and `limit` caps results; response includes `total`, `limit`, `offset`
  - `test_list_alerts_limit_exceeds_max` — `limit=201` returns 422
  - `test_deleted_alert_returns_404`
  - `test_update_alert`
  - `test_delete_alert_soft_deletes_pending_notifications` — 204, pending soft-deleted, sent/failed preserved
- [ ] **7.4** `[P]` Write integration tests for notification endpoint → satisfies US-2.1:
  - `test_list_notifications_ordered_by_triggered_at`
  - `test_list_notifications_filtered_by_status`
  - `test_list_notifications_pagination` — verifies paginated envelope fields
- [ ] **7.5** `[P]` Write unit tests for evaluator logic → satisfies US-3.1:
  - `test_creates_notification_when_threshold_exceeded`
  - `test_no_notification_when_below_threshold`
  - `test_no_duplicate_when_delta_below_renotify_threshold`
  - `test_creates_notification_when_delta_exceeds_renotify_threshold`
  - `test_continues_processing_remaining_alerts_on_error`
  - `test_evaluate_alerts_skips_when_lock_held` — second concurrent call returns immediately without querying the DB
  - `test_forecast_cache_prevents_redundant_queries` — N alerts sharing same zone/event trigger only 1 forecast query, not N
  - `test_dedup_check_uses_single_query_per_alert` — verifies `get_latest_by_dates_for_alert` is called once per alert, not once per forecast date
