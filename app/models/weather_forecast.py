import datetime

from sqlalchemy import CheckConstraint, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base_model import AuditMixin
from app.models.enums import WeatherEventType


class WeatherForecast(AuditMixin, Base):
    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint("zone", "date", "event_type", name="uq_weather_forecasts_zone_date_event"),
        CheckConstraint(
            "probability >= 0.0 AND probability <= 1.0",
            name="ck_weather_forecasts_probability",
        ),
        # Column order matches evaluator query pattern: zone → event_type → date range
        Index("ix_weather_forecasts_zone_event_date", "zone", "event_type", "date"),
        {"comment": "Weather forecast records ingested by the ingestion job"},
    )

    zone: Mapped[str] = mapped_column(String(100))
    date: Mapped[datetime.date] = mapped_column()
    # Stored as VARCHAR(50) — enum values validated in Python, not at DB level
    event_type: Mapped[WeatherEventType] = mapped_column(String(50))
    probability: Mapped[float] = mapped_column(Float)
