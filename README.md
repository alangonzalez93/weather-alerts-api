# weather-alerts-api

Backend service for configurable weather alerts based on forecast thresholds. Users define alerts for a geographic zone and weather event type; the system periodically evaluates forecasts and delivers notifications when a probability threshold is exceeded.

Built with **FastAPI**, **SQLAlchemy 2**, **PostgreSQL 16**, **Celery**, and **Redis**.

---

## Development methodology

This project was built using **Spec-Driven Development (SDD)**: every feature starts as a written spec before any code is written. The full spec set lives in [`specs/`](specs/).

Each module has three documents:

| Document | Purpose |
|----------|---------|
| `requirements.md` | User stories and acceptance criteria — the *what* |
| `design.md` | Data model, API contract, algorithms, architectural decisions — the *how* |
| `tasks.md` | Ordered implementation checklist tied to requirements — the *sequence* |

**Modules:**

- [`specs/01-setup/`](specs/01-setup/) — Project base: FastAPI, SQLAlchemy, PostgreSQL, Celery, Redis, Docker, seed script, health check
- [`specs/02-alerts/`](specs/02-alerts/) — Alerts CRUD, notification history, background evaluator, delivery pipeline

The specs capture not just what was built but *why* each decision was made — index design rationale, soft-delete semantics, cursor vs offset pagination, distributed lock strategy, and more. They serve as the authoritative reference for any future contributor.

---

## Architecture overview

```
┌─────────────┐     HTTP      ┌─────────────┐
│   FastAPI   │ ◄───────────► │  PostgreSQL │
│   (async)   │               └─────────────┘
└─────────────┘                      ▲
                                     │ sync queries
┌─────────────┐   enqueue   ┌────────┴────┐
│ Celery Beat │ ──────────► │    Redis    │
│ (scheduler) │             │  (broker)   │
└─────────────┘             └──────┬──────┘
                                   │ consume
                            ┌──────▼──────┐     ┌─────────────┐
                            │   Celery    │────►│  PostgreSQL │
                            │   Worker   │     └─────────────┘
                            └─────────────┘
```

| Service | Role |
|---------|------|
| `db` | PostgreSQL 16 — primary data store |
| `redis` | Redis 7 — Celery broker + distributed lock |
| `api` | FastAPI — REST API, runs Alembic migrations on startup |
| `worker` | Celery worker — executes `evaluate_alerts` and `deliver_notification` tasks |
| `beat` | Celery Beat — schedules `evaluate_alerts` on the configured interval |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac / Windows) or Docker Engine + Docker Compose v2 (Linux)
- Git

No other local dependencies required.

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd weather-alerts-api
```

### 2. Create the environment file

```bash
cp .env.example .env
```

The defaults work out of the box — no changes needed.

---

## Running the project

### Start all services

```bash
docker compose up --build
```

This starts everything in dependency order: **PostgreSQL → Redis → API → Worker → Beat**.

The API container automatically runs `alembic upgrade head` on startup — no manual migration step needed.

Wait until you see:

```
api-1     | INFO:     Application startup complete.
worker-1  | celery@... ready.
```

### Seed weather forecast data

In a second terminal (with services running):

```bash
docker compose run --rm api python -m app.scripts.seed_weather
```

```
Seeded 504 weather records (4 zones x 9 events x 14 days)
```

This loads forecasts for **Buenos Aires, Rosario, Córdoba and Mendoza** for the next 14 days. The following combinations are guaranteed probability ≥ 0.70 so alerts always fire in demos:

| Zone | Event type |
|------|------------|
| Buenos Aires | frost |
| Rosario | rain |
| Córdoba | hail |
| Mendoza | strong_wind |

---

## Health check

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

```json
{
    "status": "ok",
    "database": "ok",
    "redis": "ok"
}
```

Returns `503` if either PostgreSQL or Redis is unreachable.

---

## API reference

Interactive docs: **http://localhost:8000/docs**

Base path: `/api/v1`

All list endpoints return a paginated envelope:

```json
{
    "items": [...],
    "total": 42,
    "limit": 50,
    "offset": 0
}
```

---

### Alerts

#### `POST /api/v1/alerts/` — Create an alert

`event_type` values: `frost` `rain` `heavy_rain` `hail` `storm` `drought` `heat_wave` `strong_wind` `flood`

`notification_channel` values: `whatsapp` (contact must be E.164 phone) or `email` (contact must be valid email)

```bash
curl -s -X POST http://localhost:8000/api/v1/alerts/ \
  -H "Content-Type: application/json" \
  -d '{
    "field_id": "00000000-0000-0000-0000-000000000001",
    "zone": "Buenos Aires",
    "event_type": "frost",
    "threshold": 0.5,
    "notification_channel": "whatsapp",
    "contact": "+5491112345678"
  }' | python3 -m json.tool
```

```json
{
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "field_id": "00000000-0000-0000-0000-000000000001",
    "zone": "Buenos Aires",
    "event_type": "frost",
    "threshold": 0.5,
    "is_active": true,
    "notification_channel": "whatsapp",
    "contact": "+5491112345678",
    "created_at": "2026-06-02T15:00:00Z",
    "updated_at": "2026-06-02T15:00:00Z"
}
```

Save the returned `id` — you will need it for the requests below.

```bash
ALERT_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

#### `GET /api/v1/alerts/` — List alerts

`field_id` is required. Optional: `is_active` (bool), `limit` (max 200, default 50), `offset`.

```bash
curl -s "http://localhost:8000/api/v1/alerts/?field_id=00000000-0000-0000-0000-000000000001" \
  | python3 -m json.tool
```

```json
{
    "items": [
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "field_id": "00000000-0000-0000-0000-000000000001",
            "zone": "Buenos Aires",
            "event_type": "frost",
            "threshold": 0.5,
            "is_active": true,
            "notification_channel": "whatsapp",
            "contact": "+5491112345678",
            "created_at": "2026-06-02T15:00:00Z",
            "updated_at": "2026-06-02T15:00:00Z"
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0
}
```

Filter by active status:

```bash
curl -s "http://localhost:8000/api/v1/alerts/?field_id=00000000-0000-0000-0000-000000000001&is_active=true" \
  | python3 -m json.tool
```

With pagination:

```bash
curl -s "http://localhost:8000/api/v1/alerts/?field_id=00000000-0000-0000-0000-000000000001&limit=10&offset=0" \
  | python3 -m json.tool
```

---

#### `GET /api/v1/alerts/{alert_id}` — Get a single alert

```bash
curl -s "http://localhost:8000/api/v1/alerts/${ALERT_ID}" | python3 -m json.tool
```

Returns `404` if the alert does not exist or has been deleted.

---

#### `PATCH /api/v1/alerts/{alert_id}` — Update an alert

All fields are optional. If `contact` or `notification_channel` is provided, both must be included together.

Update threshold and deactivate:

```bash
curl -s -X PATCH "http://localhost:8000/api/v1/alerts/${ALERT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"threshold": 0.8, "is_active": false}' | python3 -m json.tool
```

Update contact and channel:

```bash
curl -s -X PATCH "http://localhost:8000/api/v1/alerts/${ALERT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"notification_channel": "email", "contact": "farmer@example.com"}' | python3 -m json.tool
```

Reactivate:

```bash
curl -s -X PATCH "http://localhost:8000/api/v1/alerts/${ALERT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"is_active": true}' | python3 -m json.tool
```

---

#### `DELETE /api/v1/alerts/{alert_id}` — Delete an alert

Soft-deletes the alert and all its `pending` notifications. Historical `sent`/`failed` notifications are preserved as immutable records.

```bash
curl -s -X DELETE "http://localhost:8000/api/v1/alerts/${ALERT_ID}" -w "%{http_code}\n"
```

Returns `204` on success, `404` if the alert does not exist.

---

### Notifications

#### `GET /api/v1/alerts/{alert_id}/notifications` — List notifications

Optional filters: `status` (`pending` / `sent` / `failed`), `from_date`, `to_date` (format `YYYY-MM-DD`), `limit` (max 200, default 50), `offset`. Results ordered by `triggered_at` descending.

```bash
curl -s "http://localhost:8000/api/v1/alerts/${ALERT_ID}/notifications" | python3 -m json.tool
```

```json
{
    "items": [
        {
            "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "alert_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "target_date": "2026-06-09",
            "probability": 0.83,
            "status": "sent",
            "triggered_at": "2026-06-02T15:04:18Z"
        }
    ],
    "total": 8,
    "limit": 50,
    "offset": 0
}
```

Filter by status:

```bash
curl -s "http://localhost:8000/api/v1/alerts/${ALERT_ID}/notifications?status=sent" \
  | python3 -m json.tool
```

Filter by date range:

```bash
curl -s "http://localhost:8000/api/v1/alerts/${ALERT_ID}/notifications?from_date=2026-06-03&to_date=2026-06-07" \
  | python3 -m json.tool
```

Returns `404` if the alert does not exist or has been deleted.

---

## Evaluator design

The alert evaluator is the core of the system. Its design prioritizes reliability and correctness at scale over simplicity.

### Two-phase execution

The evaluator runs in two separated phases per cycle:

```
Phase 1 — Evaluate & write
  for each active alert (cursor-based batches of 500):
    for each forecast day in the lookahead window:
      if probability >= threshold AND (no prior notification OR delta >= renotify_delta):
        INSERT notification (status=pending)
  → commit each batch to DB

Phase 2 — Enqueue
  for each pending notification in DB:
    deliver_notification.delay(notification_id)
```

**Why separate phases?** If Phase 1 and enqueuing were mixed (create → enqueue immediately), a worker crash mid-loop could leave Redis tasks pointing to notifications not yet committed to DB. By writing everything to DB first and enqueuing only after all batches commit, Redis never contains a task that doesn't have a corresponding DB row. The DB is the source of truth.

### Self-healing

If the worker crashes between Phase 1 (DB writes) and Phase 2 (Redis enqueue), the notifications remain `status=pending` in the database. The next evaluator cycle picks them up in Phase 2 and re-enqueues them automatically — no manual intervention, no lost alerts.

### Idempotency at two layers

- **Evaluation**: `get_latest_by_dates_for_alert` fetches the most recent notification per date in a single query. If the evaluator runs twice (e.g., after a crash recovery), it computes the delta against the existing notification and only creates a new one if the probability changed by more than `ALERT_RENOTIFY_DELTA`. Re-running never produces duplicate notifications.

- **Delivery**: `deliver_notification` checks `status == pending` before dispatching. If the same notification is enqueued twice (self-healing scenario), the second execution detects it's already `sent` and returns immediately.

### Distributed lock

Celery Beat fires `evaluate_alerts` on a fixed interval. If a cycle takes longer than the interval, a second instance would start while the first is still running. Without a lock both would process the same alerts concurrently — the deduplication check doesn't protect against this because both instances read before either writes. A Redis `SET NX EX` lock prevents this: if the lock is already held, the new invocation logs a warning and exits without doing any work.

### At-least-once delivery

The system guarantees at-least-once delivery: every notification will be delivered, but in a rare edge case it may be delivered twice. Specifically: if a worker successfully calls `_deliver()` (message sent) but crashes before `update_status(sent)` commits, `task_acks_late=True` re-queues the task, and the next attempt sees `status=pending` (it wasn't updated) and delivers again. For an agricultural alert system, a duplicate message is far preferable to a missed one.

---

## Testing the background evaluator

The evaluator runs automatically every `ALERT_EVAL_INTERVAL_SECONDS` (default 3600s). To trigger it immediately:

```bash
docker compose exec worker celery -A app.core.celery_app:celery_app call evaluate_alerts
```

Watch the worker logs:

```
worker-1  | [EVALUATOR] cycle complete  {"enqueued": 8, "batch_size": 500}
worker-1  | [NOTIFICATION] dispatched   {"channel": "whatsapp", "contact": "+5491112345678", "target_date": "2026-06-05", "probability": 0.83}
```

The evaluator:
1. Acquires a distributed Redis lock to prevent concurrent runs
2. Evaluates all active alerts against forecasts for the next `ALERT_LOOKAHEAD_DAYS` days (default 7)
3. Creates a `pending` notification for each day where `probability >= threshold`
4. Re-notifies only if the new probability differs by more than `ALERT_RENOTIFY_DELTA` (default 0.10)
5. Enqueues one `deliver_notification` task per notification — delivered concurrently by the worker pool

---

## Known limitations & future iterations

The following items were consciously deferred. Each is a known gap, not an oversight.

### Notification delivery is a stub

`_deliver()` logs to stdout. It is the integration point for real channel dispatch — replace with WhatsApp Business API, SendGrid, SES, or any other provider. The abstraction is already in place; the rest of the pipeline (idempotency, retries, status tracking) works end-to-end.

### No notification digest

When a zone has high probability across all 7 lookahead days, the user receives up to 7 separate messages in quick succession. A production system would batch these into a single digest: *"Frost expected in Buenos Aires: Jun 3 (83%), Jun 5 (77%), Jun 7 (81%)"*. This requires a design change — either a new `digest` notification type or a delayed-aggregation step before delivery.

### No rate limiting toward notification providers

WhatsApp Business API enforces per-number message rate limits. With 100k users, concurrent delivery at scale will hit these limits. Production would require a throttling layer between the Celery queue and the provider — a token bucket or a dedicated rate-limited delivery queue.

### Contact and channel are per-alert, not per-user

Each alert stores its own `contact` and `notification_channel`. A user with 10 alerts must specify their phone number 10 times, and updating it requires patching every alert. A user preferences model (separate from alerts) would be the natural next step.

### No uniqueness constraint per `(field_id, zone, event_type)`

A user can create multiple identical alerts for the same field, zone, and event. The evaluator would evaluate each one independently and send duplicate messages. A unique constraint or application-level deduplication would prevent this.

### Forecast data freshness not validated

The evaluator doesn't detect stale forecast data. If the ingestion job fails for 48 hours, the evaluator keeps evaluating against 2-day-old probabilities without any indication. A `max_age` check on `weather_forecasts.updated_at` before evaluation would make this visible.

### Notifications table growth

At 100k active alerts × 7 days × daily evaluations, the `notifications` table grows ~700k rows/week. Without a partitioning or archiving strategy, queries will degrade over time. PostgreSQL range partitioning by `triggered_at` (monthly partitions) and a periodic archiving job for records older than 90 days are the recommended next steps, documented in [`specs/02-alerts/design.md`](specs/02-alerts/design.md).

---

## Running the tests

Tests use [Testcontainers](https://testcontainers.com/) and spin up a real PostgreSQL instance automatically. No running services required.

```bash
uv run pytest tests/ -v
```

```
33 passed in ~15s
```

---

## Stopping the project

```bash
docker compose down       # stops containers, preserves DB data
docker compose down -v    # stops containers and wipes all volumes (clean slate)
```
