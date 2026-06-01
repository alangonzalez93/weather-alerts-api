# Re-export enums so the rest of the codebase can import from app.models directly
from app.models.enums import NotificationStatus, WeatherEventType

# Import all model classes so alembic autogenerate detects them automatically.
# When adding a new model, add its import here — that's the only registration point needed.
from app.models.weather_forecast import WeatherForecast

__all__ = ["NotificationStatus", "WeatherEventType", "WeatherForecast"]
