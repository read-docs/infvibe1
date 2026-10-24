"""Open-Meteo hourly forecast: https://open-meteo.com/en/docs"""

from dataclasses import dataclass, field


@dataclass
class HourlyWeather:
    time: float  # Unix seconds, start of the hour
    cloud_cover: float  # total, %
    cloud_low: float  # %, below ~2 km
    cloud_mid: float  # %, 2-6 km
    cloud_high: float  # %, above 6 km
    visibility_m: float
    humidity: float  # relative, %
    precip_probability: float  # %


@dataclass
class Forecast:
    timezone: str  # IANA name, e.g. "Europe/Warsaw"
    utc_offset_seconds: int
    hours: list[HourlyWeather] = field(default_factory=list)


def weather_at(f: Forecast, unix_time: float) -> HourlyWeather | None:
    """The forecast hour containing unix_time, or None if it is outside the forecast."""
    for h in f.hours:
        if h.time <= unix_time < h.time + 3600:
            return h
    return None
