"""Open-Meteo hourly forecast: https://open-meteo.com/en/docs"""

from dataclasses import dataclass, field

from skywatch.http.cache import Cache
from skywatch.http.client import HttpError, http_get, parse_json


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


def _value_at(hourly: dict, name: str, i: int, fallback: float) -> float:
    """Hourly values can be null when a model has no data for that hour."""
    arr = hourly.get(name) or []
    v = arr[i] if i < len(arr) else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else fallback


class OpenMeteo:
    def __init__(self):
        self._cache = Cache(30 * 60)

    def forecast(self, lat: float, lon: float) -> Forecast:
        """Four days of hourly data starting at local midnight today (enough for
        3-day ISS pass predictions). Raises HttpError when the API is
        unreachable or rejects the request."""
        # Two decimals is ~1 km, far finer than the weather model's grid, so nearby
        # requests share one cache entry and one upstream call.
        coords = f"latitude={lat:.2f}&longitude={lon:.2f}"
        cached = self._cache.get(coords)
        if cached is not None:
            return cached

        res = http_get(
            "https://api.open-meteo.com/v1/forecast?"
            + coords
            + "&hourly=cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
            "visibility,relative_humidity_2m,precipitation_probability"
            "&timezone=auto&timeformat=unixtime&forecast_days=4"
        )
        body = parse_json(res.body)
        if res.status != 200 or not isinstance(body, dict) or "hourly" not in body:
            # Open-Meteo error bodies look like {"error":true,"reason":"..."}.
            msg = f"Open-Meteo returned HTTP {res.status}"
            if isinstance(body, dict) and "reason" in body:
                msg = str(body["reason"])
            raise HttpError(res.status, msg)

        h = body["hourly"]
        f = Forecast(str(body.get("timezone", "GMT")), int(body.get("utc_offset_seconds", 0)))
        for i, t in enumerate(h["time"]):
            f.hours.append(
                HourlyWeather(
                    float(t),
                    _value_at(h, "cloud_cover", i, 0),
                    _value_at(h, "cloud_cover_low", i, 0),
                    _value_at(h, "cloud_cover_mid", i, 0),
                    _value_at(h, "cloud_cover_high", i, 0),
                    _value_at(h, "visibility", i, 24000),
                    _value_at(h, "relative_humidity_2m", i, 0),
                    _value_at(h, "precipitation_probability", i, 0),
                )
            )
        self._cache.put(coords, f)
        return f
