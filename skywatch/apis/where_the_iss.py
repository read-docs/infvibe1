"""The ISS position published by https://wheretheiss.at, used only to check our
own SGP4 engine against an independent source."""

from typing import NamedTuple

from skywatch.http.cache import Cache
from skywatch.http.client import HttpError, http_get, parse_json


class LiveIssPosition(NamedTuple):
    unix_time: float
    lat_deg: float
    lon_deg: float
    alt_km: float


class WhereTheIss:
    def __init__(self):
        # Cached for a few seconds: the API allows ~1 request/s.
        self._cache = Cache(4)

    def fetch(self) -> LiveIssPosition:
        """Raises HttpError on failure."""
        cached = self._cache.get("iss")
        if cached is not None:
            return cached
        res = http_get("https://api.wheretheiss.at/v1/satellites/25544")
        body = parse_json(res.body)
        if res.status != 200 or not isinstance(body, dict) or "latitude" not in body:
            raise HttpError(res.status, f"wheretheiss.at returned HTTP {res.status}")
        p = LiveIssPosition(
            float(body.get("timestamp", 0.0)),
            float(body.get("latitude", 0.0)),
            float(body.get("longitude", 0.0)),
            float(body.get("altitude", 0.0)),
        )
        self._cache.put("iss", p)
        return p
