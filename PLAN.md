# SkyWatch: Python rewrite plan (branch `python-rewrite`)

Rewrite the backend from C++ to Python. The frontend stays exactly as it is, with every feature; only the backend changes. All work happens on the `python-rewrite` branch and `main` is untouched until the merge.

## What stays the same

- **`web/` doesn't change.** Every API path, query parameter, JSON field name and the 400/502 error shape `{"error": "..."}` stays the same, so the frontend can't tell the difference.
- **Our own astronomy code stays our own.** SGP4, the Sun, Moon and planet positions, and the pass search are ported line by line. The `sgp4` library is used only as a cross-check in tests, never in the app.
- **Same external APIs and caching:** Open-Meteo forecast and geocoding, CelesTrak with the SatNOGS fallback, NASA APOD, NOAA SWPC and wheretheiss.at. Same cache times (weather 30 min, TLEs 6 h on disk in `cache/`, APOD 24 h, Kp 1 h). `config.json` is read the same way.

## Stack

Python standard library only for the app, pytest for tests:

- Python 3.15 is very new, and libraries with compiled parts (such as FastAPI's dependencies) may not have builds for it yet. The standard library always works.
- The C++ server is simple: GET routes, static files, one thread per request. `http.server.ThreadingHTTPServer`, `urllib.request`, `json` and `threading.Lock` do the same job.
- Run with `python3 -m skywatch`, no build step. pytest is the only extra install, needed only for tests.

Switching to Flask or FastAPI later only changes `server.py`.

## Layout (one module per C++ file pair)

```
skywatch/
  __main__.py        # start the server (was main.cpp)
  server.py          # routes, number parameter checks, 400/502 mapping, static files from web/
  config.py
  http/  client.py (HttpError, User-Agent, timeouts)   cache.py (TTL cache with a lock)
  apis/  nasa_apod.py  open_meteo.py  geocoding.py  celestrak.py  where_the_iss.py  swpc.py
  astro/ time.py  coords.py  sun_moon.py  planets.py  tle.py  sgp4.py  passes.py
  services/ sky_quality.py  planets.py  iss.py  starlink.py  aurora.py  json_util.py
tests/  test_time.py  test_sun_moon.py  test_planets.py  test_sgp4.py (+ sgp4_vectors.py)
        test_starlink.py  test_aurora.py  test_sky_quality.py  test_server.py
pyproject.toml       # pytest as a dev dependency, Python >= 3.11
```

About 3,100 lines of C++ should become roughly 1,800–2,200 lines of Python.

## Steps (one commit each)

1. **Branch and project setup.** Create `python-rewrite` from `main`, add `pyproject.toml` and the package layout, add `.venv/` and `__pycache__/` to `.gitignore`.
2. **Astronomy core:** time, coords, sun_moon, planets. Port the doctest cases from `test_time`, `test_sun_moon` and `test_planets` to pytest with the same expected values and tolerances.
3. **TLE and SGP4.** Turn `sgp4_vectors.inc` (Vallado's official test cases) into a Python data file and require the same km-level accuracy.
4. **Passes and the ISS and Starlink services.** Port `test_starlink`.
5. **Sky quality, planets report, aurora.** Port `test_sky_quality` and `test_aurora`.
6. **API clients and cache:** APOD with its HTML scraping and entity decoding; the CelesTrak disk cache, SatNOGS fallback, 10-minute retry wait and one lock per set.
7. **Server.** All 10 routes (`/api/health`, `apod`, `geocode`, `sky`, `planets`, `iss/now` with `?check=1`, `iss/track`, `iss/passes`, `starlink`, `aurora`), the "missing forecast just means clouds are ignored" rule, and `test_server.py`, which calls each route with fake upstream responses and checks error codes.
8. **Parity check against the C++ server.** `tools/parity.py` runs C++ on :8080 and Python on :8081, calls every endpoint at the same moment for several places (Cairo, Warsaw, Tromsø for the polar case, Sydney, and 0,0) and compares the JSON with small tolerances for times and angles. Goal: no structural differences.
9. **Remove C++ and update docs.** Delete `src/`, `CMakeLists.txt` and the C++ tests. Update the README (stack, how to run, tests). Click through all four pages in the browser and screenshot them.

## Pitfalls

- **Rounding.** C++ `std::round`/`llround` round halves away from zero; Python's `round()` rounds halves to even. Use a `round_half_away()` helper everywhere the C++ rounds, or scores, times and 0.1° values will sometimes be off by one.
- **Integer vs. float.** C++ `int(...)` truncates. Use `int()`/`math.trunc` in the same places, not `round`.
- **Number parameter checks.** Copy the exact C++ rule: `lat=abc`, `lat=`, trailing characters and out-of-range values all return 400 with the same message.
- **Concurrent requests.** `ThreadingHTTPServer` runs each request on its own thread, so the cache locks and CelesTrak's "one download per set" need `threading.Lock`.
- **Speed.** SGP4 over thousands of Starlink satellites, and the pass search at 30-second steps over up to 10 days, will be roughly 20–50× slower in pure Python. Time `/api/starlink` and `/api/iss/passes`. If they're too slow: cache the computed result for about 30 s and use plain floats instead of `Vec3` objects in the hot loop; NumPy batch propagation as a last resort.

## Done when

- All pytest tests pass, including the Vallado SGP4 cases.
- The parity script shows no differences beyond the tolerances.
- All four pages work in the browser with no console errors.
- `main` stays untouched until the merge.
