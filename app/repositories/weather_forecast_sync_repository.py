import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import WeatherEventType
from app.models.weather_forecast import WeatherForecast
from app.repositories.base import SyncBaseRepository


class WeatherForecastSyncRepository(SyncBaseRepository[WeatherForecast]):
    def __init__(self, session: Session) -> None:
        super().__init__(WeatherForecast, session)

    def get_by_zone_event_date_range(
        self,
        zone: str,
        event_type: WeatherEventType,
        date_from: datetime.date,
        date_to: datetime.date,
    ) -> list[WeatherForecast]:
        result = self.session.execute(
            select(WeatherForecast)
            .where(
                WeatherForecast.zone == zone,
                WeatherForecast.event_type == event_type,
                WeatherForecast.date >= date_from,
                WeatherForecast.date <= date_to,
                WeatherForecast.deleted == False,  # noqa: E712
            )
            .order_by(WeatherForecast.date.asc())
        )
        return list(result.scalars().all())
