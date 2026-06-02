# Requirements — Alerts Module

## Context

This spec covers the alert configuration API and the background evaluator job. It assumes the setup phase (`01-setup`) is complete: the database, async/sync SQLAlchemy sessions, Celery infrastructure, and `weather_forecasts` table are already in place.

## User Stories

---

### 1. Alert Configuration

**US-1.1** — As a user, I want to create an alert specifying a field reference, a geographic zone, a weather event type, and a probability threshold so that I am notified when that threshold is exceeded.

**US-1.2** — As a user, I want to update the threshold, activation status, contact, or notification channel of an alert so that I can adjust my notification preferences.

**US-1.3** — As a user, I want to delete an alert so that I stop receiving notifications for that event.

**Acceptance Criteria:**

- WHEN a `POST /api/v1/alerts` request contains a valid `field_id`, `zone`, `event_type`, `threshold` in [0.0, 1.0], `notification_channel`, and `contact`, the system shall create the alert with `is_active=true` and return status 201.
- WHEN `notification_channel` is `whatsapp`, the system shall validate that `contact` is a valid E.164 phone number (e.g. `+5491112345678`); if not, return status 422.
- WHEN `notification_channel` is `email`, the system shall validate that `contact` is a valid email address; if not, return status 422.
- WHEN a `POST /api/v1/alerts` request contains an invalid `event_type`, the system shall return status 422.
- WHEN a `POST /api/v1/alerts` request contains a `threshold` outside [0.0, 1.0], the system shall return status 422.
- WHEN a `POST /api/v1/alerts` request is missing a required field, the system shall return status 422 with validation details.
- WHEN a `GET /api/v1/alerts` request is received, `field_id` is required; if omitted the system shall return status 422.
- WHEN a `GET /api/v1/alerts` request includes a valid `field_id`, the system shall return only alerts matching that `field_id`.
- WHEN a `GET /api/v1/alerts` request includes an `is_active` query param, the system shall filter results accordingly.
- WHEN any list endpoint receives a `limit` value greater than 200, the system shall return status 422.
- All list endpoints shall return a paginated envelope containing `items`, `total`, `limit`, and `offset`.
- The system shall never return alerts with `deleted=true` on any GET endpoint.
- WHEN a `GET /api/v1/alerts/{id}` request references a non-existent or soft-deleted alert, the system shall return status 404.
- WHEN a `PATCH /api/v1/alerts/{id}` request contains valid partial data, the system shall update only the provided fields and return the updated alert.
- WHEN a `PATCH /api/v1/alerts/{id}` request includes `contact` or `notification_channel`, both fields must be provided together and re-validated as a pair; if either is missing, the system shall return status 422.
- WHEN a `PATCH /api/v1/alerts/{id}` request references a non-existent alert, the system shall return status 404.
- WHEN a `DELETE /api/v1/alerts/{id}` request is received for an existing alert, the system shall delete it and return status 204.
- WHEN a `DELETE /api/v1/alerts/{id}` request references a non-existent alert, the system shall return status 404.
- WHEN an alert is deleted, the system shall soft-delete all associated notifications with `status=pending`. Notifications with `status=sent` or `status=failed` are preserved as immutable historical records.

---

### 2. Notification History

**US-2.1** — As a user, I want to query the notification history for an alert so that I can review when and why I was notified.

**Acceptance Criteria:**

- WHEN a `GET /api/v1/alerts/{id}/notifications` request references a non-existent or soft-deleted alert, the system shall return status 404.
- WHEN a `GET /api/v1/alerts/{id}/notifications` request is received for a valid alert, the system shall return all non-deleted notifications ordered by `triggered_at` descending.
- WHEN optional query params `status`, `from_date`, or `to_date` are provided, the system shall filter results accordingly.
- IF a notification record exists with `status=sent` or `status=failed`, THEN the system shall never modify or delete it (historical record).

---

### 3. Automatic Alert Evaluation (Background Job)

**US-3.1** — As a system, I want to periodically evaluate all active alerts against available weather forecasts so that users are notified in a timely manner.

**Acceptance Criteria:**

- WHILE the system is running, the evaluator job shall execute at a configurable interval (default: every 3600 seconds).
- WHEN the evaluator job runs, the system shall only process alerts where `is_active=true`.
- WHEN the evaluator job runs, the system shall only evaluate `weather_forecasts` records with dates between today (UTC) and today + `ALERT_LOOKAHEAD_DAYS` (default: 7 days).
- WHEN a forecast's `probability` is greater than or equal to an alert's `threshold` AND no notification exists for that `(alert_id, target_date)` pair, the system shall create a new notification with `status=pending`.
- WHEN a notification already exists for `(alert_id, target_date)` AND the absolute difference between the current probability and the last notification's probability is less than `ALERT_RENOTIFY_DELTA` (default: 0.10), the system shall not create a new notification.
- WHEN a notification already exists for `(alert_id, target_date)` AND the absolute difference is greater than or equal to `ALERT_RENOTIFY_DELTA`, the system shall create a new notification with `status=pending`.
- WHEN a forecast's `probability` is below an alert's `threshold`, the system shall not create a notification regardless of previous notifications.
- WHEN the evaluator job fails to process an individual alert, the system shall log the error and continue processing the remaining alerts without interruption.
- WHEN the evaluator job is already running, a new invocation shall detect the active lock and exit immediately without processing any alerts or creating any notifications.
- WHEN a notification is created with `status=pending`, the system shall attempt delivery and update its status to `sent` or `failed` accordingly.
- WHEN delivery fails and retries are exhausted, the system shall mark the notification `status=failed` and emit a structured log entry with `notification_id` and failure cause.
