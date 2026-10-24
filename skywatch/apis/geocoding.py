"""Open-Meteo place search: https://open-meteo.com/en/docs/geocoding-api"""

from skywatch.errors import InvalidArgument
from skywatch.http.cache import Cache
from skywatch.http.client import HttpError, http_get, parse_json, url_encode


class Geocoding:
    def __init__(self):
        self._cache = Cache(24 * 3600)

    def search(self, query: str) -> list[dict]:
        """Up to 8 places matching the name, each {name, region, country, lat, lon}.
        Raises InvalidArgument for a query under 2 characters and HttpError on API failure."""
        # The API itself returns nothing for 1-character names.
        if len(query.encode()) < 2:
            raise InvalidArgument("search text must be at least 2 characters")
        cached = self._cache.get(query)
        if cached is not None:
            return cached

        res = http_get(
            "https://geocoding-api.open-meteo.com/v1/search?count=8&language=en&format=json&name=" + url_encode(query)
        )
        body = parse_json(res.body)
        if res.status != 200 or not isinstance(body, dict):
            msg = f"Geocoding API returned HTTP {res.status}"
            if isinstance(body, dict) and "reason" in body:
                msg = str(body["reason"])
            raise HttpError(res.status, msg)

        # "results" is absent when nothing matches.
        places = [
            {
                "name": r.get("name", ""),
                "region": r.get("admin1", ""),
                "country": r.get("country", ""),
                "lat": float(r.get("latitude", 0.0)),
                "lon": float(r.get("longitude", 0.0)),
            }
            for r in body.get("results", [])
        ]
        self._cache.put(query, places)
        return places
