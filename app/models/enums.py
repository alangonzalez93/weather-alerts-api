import enum


# StrEnum (Python 3.11+) serializes values as strings in JSON and means adding
# new values only requires a code change — no DB migration needed
class WeatherEventType(enum.StrEnum):
    frost = "frost"
    rain = "rain"
    heavy_rain = "heavy_rain"
    hail = "hail"
    storm = "storm"
    drought = "drought"
    heat_wave = "heat_wave"
    strong_wind = "strong_wind"
    flood = "flood"


class NotificationStatus(enum.StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class NotificationChannel(enum.StrEnum):
    whatsapp = "whatsapp"
    email = "email"
