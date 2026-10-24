"""Routes, query parameter checks, error mapping and the static frontend."""

import json
import math
import re
import sys
import time
import urllib.parse
from collections.abc import Callable
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from skywatch.apis.celestrak import Celestrak
from skywatch.apis.geocoding import Geocoding
from skywatch.apis.nasa_apod import NasaApod
from skywatch.apis.open_meteo import Forecast, OpenMeteo
from skywatch.apis.swpc import Swpc
from skywatch.apis.where_the_iss import WhereTheIss
from skywatch.astro.coords import Geodetic
from skywatch.config import Config
from skywatch.errors import InvalidArgument
from skywatch.http.client import HttpError
from skywatch.services.aurora import aurora_report
from skywatch.services.iss import iss_check, iss_now, iss_passes, iss_track
from skywatch.services.planets import planets_report
from skywatch.services.sky_quality import sky_report
from skywatch.services.starlink import starlink_report

Params = dict[str, str]
Response = tuple[int, object]

# What C's strtod accepts in full: decimal or hex numbers, inf and nan.
_NUMBER = re.compile(
    r"\s*[+-]?(?:(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|0[xX](?:[0-9a-fA-F]+\.?[0-9a-fA-F]*|\.[0-9a-fA-F]+)(?:[pP][+-]?\d+)?|inf(?:inity)?|nan(?:\([0-9A-Za-z_]*\))?)",
    re.IGNORECASE,
)


def number_param(params: Params, name: str, lo: float, hi: float) -> float:
    """A required numeric query parameter within [lo, hi]; raises InvalidArgument."""
    raw = params.get(name, "")
    value = math.nan
    if _NUMBER.fullmatch(raw):
        text = raw.strip()
        try:
            value = float.fromhex(text) if "x" in text.lower() else float(text)
        except (ValueError, OverflowError):
            pass
    if not (lo <= value <= hi):
        raise InvalidArgument(f"{name} must be a number between {int(lo)} and {int(hi)}")
    return value


def _unix_now() -> float:
    return time.time()


class SkyWatch:
    """The API: one method per route, each taking the query parameters and
    returning (status, JSON body)."""

    def __init__(self, cfg: Config, root: Path, clock: Callable[[], float] = _unix_now):
        self.apod = NasaApod(cfg.nasa_api_key)
        self.weather = OpenMeteo()
        self.geocoding = Geocoding()
        self.celestrak = Celestrak(root / "cache")
        self.where_the_iss = WhereTheIss()
        self.swpc = Swpc()
        self.now = clock
        self.routes: dict[str, Callable[[Params], object]] = {
            "/api/health": lambda p: {"status": "ok"},
            "/api/geocode": lambda p: self.geocoding.search(p.get("q", "")),
            "/api/sky": self.sky,
            "/api/planets": self.planets,
            "/api/iss/now": self.iss_now,
            "/api/iss/track": self.iss_track,
            "/api/iss/passes": self.iss_passes,
            "/api/starlink": self.starlink,
            "/api/aurora": self.aurora,
        }

    def handle(self, path: str, params: Params) -> Response | None:
        """Runs a route, turning bad input into 400 and upstream API failures
        into 502. None when no route matches."""
        if path == "/api/apod":
            try:
                return 200, self.apod.fetch(params.get("date", ""))
            except InvalidArgument as e:
                return 400, {"error": str(e)}
            except HttpError as e:
                # A 4xx from NASA (e.g. date out of range) is the client's fault; anything else is upstream.
                return (400 if 400 <= e.status < 500 else 502), {"error": str(e)}
        route = self.routes.get(path)
        if route is None:
            return None
        try:
            return 200, route(params)
        except InvalidArgument as e:
            return 400, {"error": str(e)}
        except HttpError as e:
            return 502, {"error": str(e)}

    def optional_forecast(self, lat: float, lon: float) -> Forecast | None:
        """Planets and aurora are still worth showing when the weather API is
        down, just without clouds."""
        try:
            return self.weather.forecast(lat, lon)
        except HttpError as e:
            print(f"warning: no forecast, ignoring clouds: {e}", file=sys.stderr)
            return None

    @staticmethod
    def location(p: Params) -> tuple[float, float]:
        return number_param(p, "lat", -90, 90), number_param(p, "lon", -180, 180)

    def sky(self, p: Params):
        lat, lon = self.location(p)
        return sky_report(self.weather.forecast(lat, lon), lat, lon, self.now())

    def planets(self, p: Params):
        lat, lon = self.location(p)
        return planets_report(lat, lon, self.now(), self.optional_forecast(lat, lon))

    def iss_now(self, p: Params):
        # Optional observer from ?lat=&lon=; both or neither must be given.
        observer = Geodetic(*self.location(p), 0) if "lat" in p or "lon" in p else None
        iss = self.celestrak.iss()
        out = iss_now(iss, self.now(), observer)
        # The comparison is optional: the live API being down shouldn't hide our own result.
        if p.get("check") == "1":
            try:
                out["check"] = iss_check(iss.satellites[0], self.where_the_iss.fetch())
            except HttpError as e:
                out["check"] = {"error": str(e)}
        return out

    def iss_track(self, p: Params):
        minutes = number_param(p, "minutes", 1, 300) if "minutes" in p else 95
        return iss_track(self.celestrak.iss().satellites[0], self.now(), minutes)

    def iss_passes(self, p: Params):
        lat, lon = self.location(p)
        days = number_param(p, "days", 1, 10) if "days" in p else 3
        forecast = self.optional_forecast(lat, lon)
        return iss_passes(self.celestrak.iss().satellites[0], Geodetic(lat, lon, 0), self.now(), days, forecast)

    def starlink(self, p: Params):
        lat, lon = self.location(p)
        starlink = self.celestrak.starlink()  # first: no point fetching weather if this fails
        return starlink_report(starlink, lat, lon, self.now(), self.optional_forecast(lat, lon))

    def aurora(self, p: Params):
        lat, lon = self.location(p)
        forecast = self.optional_forecast(lat, lon)
        return aurora_report(self.swpc.fetch(), forecast, lat, lon, self.now())


def _finite(value):
    """NaN and infinity become null, as they would in the C++ server."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


def dump_json(body: object) -> bytes:
    try:
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except ValueError:
        text = json.dumps(_finite(body), ensure_ascii=False, separators=(",", ":"))
    return text.encode()


def make_server(app: SkyWatch, web_root: Path, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            if url.path.startswith("/api/"):
                # The first value wins when a parameter is repeated.
                params: Params = {}
                for k, v in urllib.parse.parse_qsl(url.query, keep_blank_values=True):
                    params.setdefault(k, v)
                try:
                    result = app.handle(url.path, params)
                except Exception as e:  # a bug, not bad input: don't take the server down
                    print(f"error: {url.path}: {e!r}", file=sys.stderr)
                    result = 500, {"error": "internal server error"}
                if result is not None:
                    status, body = result
                    data = dump_json(body)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            super().do_GET()

        def list_directory(self, path):
            self.send_error(404)
            return None

        def log_message(self, format, *args):
            pass  # quiet, like the C++ server

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
