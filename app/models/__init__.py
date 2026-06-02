# Re-export enums so the rest of the codebase can import from app.models directly
# Import all model classes so alembic autogenerate detects them automatically.
# When adding a new model, add its import here — that's the only registration point needed.
from app.models.alert import Alert
from app.models.enums import NotificationChannel, NotificationStatus, WeatherEventType
from app.models.notification import Notification
from app.models.weather_forecast import WeatherForecast

__all__ = [
    "Alert",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
    "WeatherEventType",
    "WeatherForecast",
]
