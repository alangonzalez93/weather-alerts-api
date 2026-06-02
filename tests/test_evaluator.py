"""Unit tests for evaluator logic.

These tests exercise _evaluate_alert and evaluate_alerts directly using mocks —
no DB or Redis needed.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.tasks.evaluate_alerts import _evaluate_alert, evaluate_alerts

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_alert(threshold=0.5):
    alert = MagicMock()
    alert.id = uuid.uuid4()
    alert.zone = "Buenos Aires"
    alert.event_type = "frost"
    alert.threshold = threshold
    return alert


def _make_forecast(probability, days_offset=1):
    f = MagicMock()
    f.date = date.today() + timedelta(days=days_offset)
    f.probability = probability
    return f


def _make_notification_repo(latest_by_date=None):
    repo = MagicMock()
    repo.get_latest_by_dates_for_alert.return_value = latest_by_date or {}
    return repo


# ── _evaluate_alert ───────────────────────────────────────────────────────────


def test_creates_notification_when_threshold_exceeded():
    alert = _make_alert(threshold=0.5)
    forecast = _make_forecast(probability=0.8)
    repo = _make_notification_repo()

    _evaluate_alert(alert, [forecast], repo, date.today(), date.today() + timedelta(days=7))

    repo.create.assert_called_once()
    created = repo.create.call_args[0][0]
    assert created.alert_id == alert.id
    assert created.target_date == forecast.date
    assert created.probability == 0.8


def test_no_notification_when_below_threshold():
    alert = _make_alert(threshold=0.9)
    forecast = _make_forecast(probability=0.5)
    repo = _make_notification_repo()

    _evaluate_alert(alert, [forecast], repo, date.today(), date.today() + timedelta(days=7))

    repo.create.assert_not_called()


def test_no_duplicate_when_delta_below_renotify_threshold():
    alert = _make_alert(threshold=0.5)
    forecast = _make_forecast(probability=0.75)

    existing = MagicMock()
    existing.probability = 0.70  # delta = 0.05 < default 0.10

    repo = _make_notification_repo(latest_by_date={forecast.date: existing})

    _evaluate_alert(alert, [forecast], repo, date.today(), date.today() + timedelta(days=7))

    repo.create.assert_not_called()


def test_creates_notification_when_delta_exceeds_renotify_threshold():
    alert = _make_alert(threshold=0.5)
    forecast = _make_forecast(probability=0.90)

    existing = MagicMock()
    existing.probability = 0.70  # delta = 0.20 >= 0.10

    repo = _make_notification_repo(latest_by_date={forecast.date: existing})

    _evaluate_alert(alert, [forecast], repo, date.today(), date.today() + timedelta(days=7))

    repo.create.assert_called_once()


def test_continues_processing_remaining_alerts_on_error():
    alert1 = _make_alert()
    alert2 = _make_alert()
    forecast = _make_forecast(probability=0.8)

    repo = MagicMock()
    repo.get_latest_by_dates_for_alert.side_effect = [Exception("DB error"), {}]

    date_from = date.today()
    date_to = date.today() + timedelta(days=7)

    # alert1 raises, alert2 should still be processed
    try:
        _evaluate_alert(alert1, [forecast], repo, date_from, date_to)
    except Exception:
        pass

    _evaluate_alert(alert2, [forecast], repo, date_from, date_to)

    repo.create.assert_called_once()
    assert repo.create.call_args[0][0].alert_id == alert2.id


# ── distributed lock ─────────────────────────────────────────────────────────


def test_evaluate_alerts_skips_when_lock_held():
    with (
        patch("app.tasks.evaluate_alerts.redis_client") as mock_redis,
        patch("app.tasks.evaluate_alerts._run_evaluation") as mock_run,
    ):
        mock_redis.set.return_value = None  # lock not acquired

        evaluate_alerts()

        mock_run.assert_not_called()


def test_evaluate_alerts_acquires_and_releases_lock():
    with (
        patch("app.tasks.evaluate_alerts.redis_client") as mock_redis,
        patch("app.tasks.evaluate_alerts._run_evaluation"),
    ):
        mock_redis.set.return_value = True

        evaluate_alerts()

        mock_redis.delete.assert_called_once_with("lock:evaluate_alerts")


# ── forecast cache ────────────────────────────────────────────────────────────


def test_forecast_cache_prevents_redundant_queries():
    """N alerts sharing same (zone, event_type) trigger only 1 forecast query."""
    with (
        patch("app.tasks.evaluate_alerts.redis_client") as mock_redis,
        patch("app.tasks.evaluate_alerts.get_sync_session") as mock_ctx,
    ):
        mock_redis.set.return_value = True

        session = MagicMock()
        mock_ctx.return_value.__enter__ = MagicMock(return_value=session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        alert_repo = MagicMock()
        forecast_repo = MagicMock()
        notification_repo = MagicMock()
        notification_repo.get_latest_by_dates_for_alert.return_value = {}
        notification_repo.get_pending.return_value = []

        # 3 alerts all with same zone/event_type
        alerts = [_make_alert() for _ in range(3)]
        alert_repo.get_active.side_effect = [alerts, []]
        forecast_repo.get_by_zone_event_date_range.return_value = []

        task = "app.tasks.evaluate_alerts"
        with (
            patch(f"{task}.AlertSyncRepository", return_value=alert_repo),
            patch(f"{task}.WeatherForecastSyncRepository", return_value=forecast_repo),
            patch(f"{task}.NotificationSyncRepository", return_value=notification_repo),
        ):
            evaluate_alerts()

        # Only 1 forecast query for 3 alerts sharing the same zone/event_type
        assert forecast_repo.get_by_zone_event_date_range.call_count == 1


def test_dedup_check_uses_single_query_per_alert():
    """get_latest_by_dates_for_alert called once per alert, not once per forecast date."""
    alert = _make_alert(threshold=0.5)
    forecasts = [_make_forecast(probability=0.8, days_offset=i) for i in range(1, 8)]
    repo = _make_notification_repo()

    _evaluate_alert(alert, forecasts, repo, date.today(), date.today() + timedelta(days=7))

    # Should be called exactly once regardless of how many forecasts exceed threshold
    assert repo.get_latest_by_dates_for_alert.call_count == 1
