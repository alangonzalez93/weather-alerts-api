from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WeatherEventType
from app.models.weather_forecast import WeatherForecast
from app.repositories.weather_forecast_repository import WeatherForecastRepository


def _today():
    return datetime.now(tz=UTC).date()


def _forecast(
    zone: str, event_type: WeatherEventType, probability: float, offset: int = 0
) -> WeatherForecast:
    return WeatherForecast(
        zone=zone,
        date=_today() + timedelta(days=offset),
        event_type=event_type,
        probability=probability,
    )


async def test_upsert_creates_forecast(db_session: AsyncSession) -> None:
    repo = WeatherForecastRepository(db_session)

    created = await repo.upsert(_forecast("Buenos Aires", WeatherEventType.frost, 0.85))

    assert created.id is not None
    assert created.zone == "Buenos Aires"
    assert created.event_type == WeatherEventType.frost
    assert created.probability == 0.85


async def test_upsert_updates_probability_on_conflict(db_session: AsyncSession) -> None:
    # Same (zone, date, event_type) — second upsert must update, not duplicate
    repo = WeatherForecastRepository(db_session)
    await repo.upsert(_forecast("Mendoza", WeatherEventType.hail, 0.50))

    updated = await repo.upsert(_forecast("Mendoza", WeatherEventType.hail, 0.90))

    assert updated.probability == 0.90


async def test_upsert_different_event_types_create_separate_forecasts(
    db_session: AsyncSession,
) -> None:
    repo = WeatherForecastRepository(db_session)

    r1 = await repo.upsert(_forecast("Rosario", WeatherEventType.rain, 0.60))
    r2 = await repo.upsert(_forecast("Rosario", WeatherEventType.flood, 0.40))

    assert r1.id != r2.id


async def test_get_by_zone_event_date_range_returns_matching_forecasts(
    db_session: AsyncSession,
) -> None:
    repo = WeatherForecastRepository(db_session)
    today = _today()

    # Insert 5 days of rain forecasts for Córdoba
    for offset in range(5):
        await repo.upsert(_forecast("Córdoba", WeatherEventType.rain, 0.5 + offset * 0.05, offset))

    results = await repo.get_by_zone_event_date_range(
        zone="Córdoba",
        event_type=WeatherEventType.rain,
        date_from=today,
        date_to=today + timedelta(days=2),  # only first 3 days
    )

    assert len(results) == 3
    assert all(r.zone == "Córdoba" for r in results)
    assert all(r.event_type == WeatherEventType.rain for r in results)
    # results must be ordered by date ascending
    assert results[0].date <= results[1].date <= results[2].date


async def test_get_by_zone_event_date_range_excludes_other_zones(
    db_session: AsyncSession,
) -> None:
    repo = WeatherForecastRepository(db_session)

    await repo.upsert(_forecast("Buenos Aires", WeatherEventType.drought, 0.70))
    await repo.upsert(_forecast("Mendoza", WeatherEventType.drought, 0.80))

    results = await repo.get_by_zone_event_date_range(
        zone="Buenos Aires",
        event_type=WeatherEventType.drought,
        date_from=_today(),
        date_to=_today(),
    )

    assert len(results) == 1
    assert results[0].zone == "Buenos Aires"
