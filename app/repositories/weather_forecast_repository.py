from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WeatherEventType
from app.models.weather_forecast import WeatherForecast
from app.repositories.base import BaseRepository


class WeatherForecastRepository(BaseRepository[WeatherForecast]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(WeatherForecast, session)

    async def get_by_zone_event_date_range(
        self,
        zone: str,
        event_type: WeatherEventType,
        date_from: date,
        date_to: date,
    ) -> list[WeatherForecast]:
        result = await self.session.execute(
            select(WeatherForecast)
            .where(
                WeatherForecast.zone == zone,
                WeatherForecast.event_type == event_type,
                WeatherForecast.date >= date_from,
                WeatherForecast.date <= date_to,
            )
            .order_by(WeatherForecast.date)
        )
        return list(result.scalars().all())

    async def upsert(self, forecast: WeatherForecast) -> WeatherForecast:
        # on_conflict_do_update mirrors the ingestion job's behaviour:
        # same (zone, date, event_type) updates the probability instead of failing
        stmt = (
            insert(WeatherForecast)
            .values(
                zone=forecast.zone,
                date=forecast.date,
                event_type=forecast.event_type,
                probability=forecast.probability,
            )
            .on_conflict_do_update(
                constraint="uq_weather_forecasts_zone_date_event",
                set_={
                    "probability": forecast.probability,
                    "updated_at": func.now(),
                },
            )
            .returning(WeatherForecast)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()
