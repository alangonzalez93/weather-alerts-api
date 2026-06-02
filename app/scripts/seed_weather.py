"""Idempotent seed script for weather_forecasts mock data.

Usage:
    uv run python -m app.scripts.seed_weather
"""

import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.core.database_sync import get_sync_session
from app.models import WeatherEventType
from app.models.weather_forecast import WeatherForecast

ZONES = ["Buenos Aires", "Rosario", "Córdoba", "Mendoza"]
LOOKAHEAD_DAYS = 14

# Guaranteed high-probability events per zone so alerts can always be triggered in tests
HIGH_PROBABILITY_EVENTS = {
    ("Buenos Aires", WeatherEventType.frost),
    ("Rosario", WeatherEventType.rain),
    ("Córdoba", WeatherEventType.hail),
    ("Mendoza", WeatherEventType.strong_wind),
}


def _build_records(today: date) -> list[dict]:
    records = []
    for day_offset in range(LOOKAHEAD_DAYS):
        forecast_date = today + timedelta(days=day_offset)
        for zone in ZONES:
            for event_type in WeatherEventType:
                # Pin certain zone+event combos to high probability to ensure testability
                if (zone, event_type) in HIGH_PROBABILITY_EVENTS:
                    probability = round(random.uniform(0.7, 1.0), 2)
                else:
                    probability = round(random.uniform(0.0, 0.85), 2)

                records.append(
                    {
                        "zone": zone,
                        "date": forecast_date,
                        "event_type": event_type.value,
                        "probability": probability,
                        "updated_at": datetime.now(tz=UTC),
                        "created_at": datetime.now(tz=UTC),
                    }
                )
    return records


def run() -> None:
    today = datetime.now(tz=UTC).date()
    records = _build_records(today)

    with get_sync_session() as session:
        # Upsert — re-running the script updates probabilities without creating duplicates
        stmt = (
            insert(WeatherForecast)
            .values(records)
            .on_conflict_do_update(
                constraint="uq_weather_forecasts_zone_date_event",
                set_={
                    "probability": insert(WeatherForecast).excluded.probability,
                    "updated_at": insert(WeatherForecast).excluded.updated_at,
                },
            )
        )
        session.execute(stmt)

    print(
        f"Seeded {len(records)} weather records "
        f"({len(ZONES)} zones x {len(WeatherEventType)} events x {LOOKAHEAD_DAYS} days)"
    )


if __name__ == "__main__":
    run()
