"""Every route through the real HTTP server, with fake upstream APIs."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from skywatch.apis import celestrak, geocoding, nasa_apod, open_meteo, swpc, where_the_iss
from skywatch.config import Config
from skywatch.http.client import HttpError, HttpResponse
from skywatch.server import SkyWatch, make_server

NOW = 1792723800  # 2026-10-23 02:50 UTC
ISS_TLE = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   26294.95113894  .00010428  00000-0  19720-3 0  9990\n"
    "2 25544  51.6330  32.7943 0006789 293.2617  66.7657 15.48983994591404\n"
)
STARLINK_TLE = (
    "STARLINK-3100\n"
    "1 49144U 21082Q   26295.16668980  .00038120  00000-0  22380-2 0  9994\n"
    "2 49144  70.0014  83.1836 0003596 259.3597  48.0136 15.11538324  5750\n"
)


def forecast_body() -> str:
    times = [NOW - NOW % 3600 - 12 * 3600 + i * 3600 for i in range(96)]
    hourly = {"time": times}
    for name in ("cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high", "precipitation_probability"):
        hourly[name] = [0] * 96
    hourly["visibility"] = [24000] * 96
    hourly["relative_humidity_2m"] = [None] * 96  # nulls fall back to defaults
    return json.dumps({"timezone": "Europe/Warsaw", "utc_offset_seconds": 7200, "hourly": hourly})


ARTICLE = (
    '<meta property="og:title" content="APOD: 2026 October 20 - Orion&#8217;s Belt - NASA Science">'
    '<meta property="og:image" content="https://science.nasa.gov/orion.jpg">'
    "<p><strong>Explanation:</strong> Three <a>stars</a> . &amp; more<br><br>Second."
    "<strong>Tomorrow's picture: x</strong></p>"
    '<div class="media-detail-hero__meta-row"><th>Image Credit:</th> <td>Image Credit: A. Astronomer</td>'
)


class Upstream:
    """Answers http_get by URL prefix; a route set to an exception raises it."""

    def __init__(self):
        self.routes = {
            "https://api.open-meteo.com/": (200, forecast_body()),
            "https://geocoding-api.open-meteo.com/": (
                200,
                json.dumps({"results": [{"name": "Warsaw", "admin1": "Mazovia", "country": "Poland", "latitude": 52.23, "longitude": 21.01}]}),
            ),
            "https://celestrak.org/NORAD/elements/gp.php?CATNR": (200, ISS_TLE),
            "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink": (200, STARLINK_TLE),
            "https://db.satnogs.org/": HttpError(0, "down"),
            "https://api.wheretheiss.at/": (
                200,
                json.dumps({"timestamp": NOW, "latitude": 10.0, "longitude": 20.0, "altitude": 420.0}),
            ),
            "https://services.swpc.noaa.gov/products/": (
                200,
                json.dumps([{"time_tag": "2026-10-23T00:00:00", "kp": 3.33, "observed": "observed"}]),
            ),
            "https://services.swpc.noaa.gov/json/": (200, json.dumps([{"estimated_kp": 2.67}])),
            "https://api.nasa.gov/": (
                200,
                json.dumps({"date": "2026-10-20", "title": "T", "explanation": "E", "media_type": "image", "url": "https://x/a.jpg"}),
            ),
            "https://apod.nasa.gov/": (200, ARTICLE),
        }
        self.calls: list[str] = []

    def __call__(self, url: str) -> HttpResponse:
        self.calls.append(url)
        for prefix, answer in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return HttpResponse(*answer)
        raise HttpError(0, f"unexpected request: {url}")


@pytest.fixture
def upstream(monkeypatch):
    fake = Upstream()
    for module in (celestrak, geocoding, nasa_apod, open_meteo, swpc, where_the_iss):
        monkeypatch.setattr(module, "http_get", fake)
    return fake


@pytest.fixture
def get(upstream, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>SkyWatch</h1>")
    app = SkyWatch(Config(), tmp_path, clock=lambda: NOW)
    server = make_server(app, web, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def fetch(path: str):
        try:
            with urllib.request.urlopen(base + path) as res:
                body = res.read()
                status, ctype = res.status, res.headers["Content-Type"]
        except urllib.error.HTTPError as e:
            body, status, ctype = e.read(), e.code, e.headers["Content-Type"]
        if ctype == "application/json":
            return status, json.loads(body)
        return status, body.decode()

    yield fetch
    server.shutdown()
    server.server_close()


def test_health(get):
    assert get("/api/health") == (200, {"status": "ok"})


@pytest.mark.parametrize(
    "query",
    ["lat=abc&lon=1", "lat=&lon=1", "lon=1", "lat=1x&lon=1", "lat=91&lon=1", "lat=5%20&lon=1", "lat=nan&lon=1", "lat=inf&lon=1"],
)
def test_bad_latitude_is_400_with_the_cpp_message(get, query):
    assert get(f"/api/sky?{query}") == (400, {"error": "lat must be a number between -90 and 90"})


@pytest.mark.parametrize("query", ["lat=%205&lon=1", "lat=0x10&lon=1", "lat=1e1&lon=1", "lat=-.5&lon=1"])
def test_numbers_strtod_accepts_are_fine(get, query):
    assert get(f"/api/sky?{query}")[0] == 200


def test_sky(get):
    status, body = get("/api/sky?lat=52.23&lon=21.01")
    assert status == 200
    assert body["location"]["timezone"] == "Europe/Warsaw"
    assert body["now"] == NOW
    assert len(body["hours"]) >= 13
    assert body["hours"][0]["humidity"] == 0  # null in the forecast


def test_sky_needs_the_forecast(get, upstream):
    upstream.routes["https://api.open-meteo.com/"] = (400, json.dumps({"error": True, "reason": "bad coords"}))
    assert get("/api/sky?lat=52.23&lon=21.01") == (502, {"error": "bad coords"})


def test_planets_without_weather_ignore_clouds(get, upstream):
    upstream.routes["https://api.open-meteo.com/"] = HttpError(0, "down")
    status, body = get("/api/planets?lat=52.23&lon=21.01")
    assert status == 200
    assert body["weather"] is False
    assert len(body["bodies"]) == 8


def test_iss_now(get, upstream):
    status, body = get("/api/iss/now")
    assert status == 200
    assert "look" not in body and "check" not in body
    assert body["tle"]["source"] == "CelesTrak"

    # The live API being down doesn't hide our own result.
    upstream.routes["https://api.wheretheiss.at/"] = HttpError(0, "live API down")
    assert get("/api/iss/now?check=1")[1]["check"] == {"error": "live API down"}
    upstream.routes["https://api.wheretheiss.at/"] = (
        200,
        json.dumps({"timestamp": NOW, "latitude": 10.0, "longitude": 20.0, "altitude": 420.0}),
    )

    status, body = get("/api/iss/now?lat=52.23&lon=21.01&check=1")
    assert status == 200
    assert set(body["look"]) == {"alt", "az", "direction", "range_km"}
    assert body["check"]["source"] == "wheretheiss.at"

    # Both or neither of lat and lon.
    assert get("/api/iss/now?lat=52")[0] == 400


def test_iss_orbits_are_downloaded_once_and_cached_on_disk(get, upstream, tmp_path):
    get("/api/iss/now")
    get("/api/iss/track")
    assert sum("CATNR" in u for u in upstream.calls) == 1
    assert (tmp_path / "cache" / "tle-iss.txt").read_text().startswith("# ")


def test_iss_falls_back_to_satnogs(get, upstream):
    upstream.routes["https://celestrak.org/NORAD/elements/gp.php?CATNR"] = (503, "busy")
    lines = ISS_TLE.splitlines()
    upstream.routes["https://db.satnogs.org/"] = (200, json.dumps([{"tle0": "0 ISS (ZARYA)", "tle1": lines[1], "tle2": lines[2]}]))
    assert get("/api/iss/now")[1]["tle"]["source"] == "SatNOGS"


def test_iss_track(get):
    status, body = get("/api/iss/track")
    assert status == 200
    assert len(body["points"]) == 95 * 2 * 2 + 1  # ±95 minutes every 30 s
    assert get("/api/iss/track?minutes=0") == (400, {"error": "minutes must be a number between 1 and 300"})


def test_iss_passes(get):
    status, body = get("/api/iss/passes?lat=52.23&lon=21.01&days=1")
    assert status == 200
    assert body["passes"]
    first = body["passes"][0]
    assert first["rise"]["time"] < first["peak"]["time"] < first["set"]["time"]
    assert get("/api/iss/passes?lat=52.23&lon=21.01&days=11")[0] == 400


def test_starlink(get, upstream):
    status, body = get("/api/starlink?lat=52.23&lon=21.01")
    assert status == 200
    assert body["counts"]["total"] == 1


def test_starlink_without_orbits_is_502(get, upstream):
    upstream.routes["https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink"] = HttpError(0, "timeout")
    status, body = get("/api/starlink?lat=52.23&lon=21.01")
    assert status == 502
    assert "couldn't download satellite orbits" in body["error"]
    # After a failure the next request doesn't wait for another download.
    calls = len(upstream.calls)
    assert get("/api/starlink?lat=52.23&lon=21.01")[0] == 502
    assert not any("GROUP=starlink" in u for u in upstream.calls[calls:])


def test_aurora(get, upstream):
    status, body = get("/api/aurora?lat=52.23&lon=21.01")
    assert status == 200
    assert body["now"]["kp"] == 2.67
    assert body["tonight"]["weather"] is True


def test_aurora_needs_the_kp_data(get, upstream):
    upstream.routes["https://services.swpc.noaa.gov/products/"] = (500, "")
    assert get("/api/aurora?lat=52.23&lon=21.01") == (502, {"error": "NOAA SWPC returned HTTP 500"})


def test_geocode(get):
    assert get("/api/geocode?q=W") == (400, {"error": "search text must be at least 2 characters"})
    status, body = get("/api/geocode?q=Warsaw")
    assert status == 200
    assert body == [{"name": "Warsaw", "region": "Mazovia", "country": "Poland", "lat": 52.23, "lon": 21.01}]


def test_apod(get, upstream):
    status, body = get("/api/apod?date=2026-10-20")
    assert status == 200
    assert body["title"] == "T"
    assert body["page_url"] == "https://apod.nasa.gov/apod/ap261020.html"
    assert get("/api/apod?date=yesterday") == (400, {"error": "date must be YYYY-MM-DD"})


def test_apod_errors(get, upstream):
    upstream.routes["https://api.nasa.gov/"] = (400, json.dumps({"code": 400, "msg": "Date must be after 1995"}))
    assert get("/api/apod?date=1990-01-01") == (400, {"error": "Date must be after 1995"})
    upstream.routes["https://api.nasa.gov/"] = (503, "")
    assert get("/api/apod?date=2026-10-19") == (502, {"error": "NASA API returned HTTP 503"})


def test_apod_recovers_from_the_website_when_nasa_shows_its_logo(get, upstream):
    upstream.routes["https://api.nasa.gov/"] = (
        200,
        json.dumps({"date": "2026-10-20", "title": "x", "explanation": "wrong day", "url": "https://x/nasa-logo.svg"}),
    )
    status, body = get("/api/apod?date=2026-10-20")
    assert status == 200
    assert body["title"] == "Orion’s Belt"
    assert body["url"] == "https://science.nasa.gov/orion.jpg"
    assert body["explanation"] == "Three stars. & more\n\nSecond."
    assert body["copyright"] == "A. Astronomer"
    assert body["media_missing"] is False

    upstream.routes["https://apod.nasa.gov/"] = (200, "<html>index</html>")
    status, body = get("/api/apod?date=2026-10-21")
    assert body["media_missing"] is True
    assert body["url"] == ""


def test_static_files(get):
    assert get("/") == (200, "<h1>SkyWatch</h1>")
    assert get("/missing.js")[0] == 404
    assert get("/api/unknown")[0] == 404
