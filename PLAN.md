# SkyWatch: project plan

A C++ web app that tells you what you can see in the sky tonight from any location: when the sky is clearest, which planets are up, when the ISS flies over, where Starlink satellites are, and NASA's picture of the day.

## 1. Requirements

| Requirement | How it is met |
|---|---|
| Written in C++ | The whole backend (HTTP server, API clients, all astronomy math) is C++17 |
| Has a website | The C++ server also serves a static HTML/CSS/JS frontend |
| Uses 3 APIs | Open-Meteo (weather), CelesTrak (satellite orbits), NASA APOD, plus Open-Meteo Geocoding and NOAA SWPC for extras |
| Screen 1: sky visibility + best hour today | Hourly "seeing score" from weather + darkness + Moon |
| Planets, ISS, Starlink on screen 1 | Computed in C++ from orbital data |
| Own ISS flight engine | SGP4 orbit propagator written in C++, fed with TLE data from CelesTrak |
| Screen with NASA picture of the day | NASA APOD API |
| One extra feature | Aurora & space weather screen (section 5) |

## 2. Tech stack

- **Language:** C++17
- **Build:** CMake (not installed yet: `brew install cmake openssl`)
- **HTTP server and client:** [cpp-httplib](https://github.com/yhirose/cpp-httplib), header-only, HTTPS via OpenSSL
- **JSON:** [nlohmann/json](https://github.com/nlohmann/json), header-only
- **Tests:** doctest or Catch2, header-only
- **Frontend:** plain HTML + CSS + JavaScript (no framework). Leaflet + OpenStreetMap for the location picker and the ISS ground track map. A `<canvas>` for the sky dome chart.

All libraries are header-only, pulled in with CMake `FetchContent`, so the build stays a single `cmake --build`.

## 3. External APIs

| # | API | Key? | Used for |
|---|---|---|---|
| 1 | **Open-Meteo Forecast** `api.open-meteo.com/v1/forecast` | no | Hourly cloud cover (low/mid/high), visibility, humidity, precipitation probability |
| 2 | **CelesTrak GP** `celestrak.org/NORAD/elements/gp.php?CATNR=25544` and `?GROUP=starlink` | no | TLE orbital elements for the ISS and every Starlink satellite |
| 3 | **NASA APOD** `api.nasa.gov/planetary/apod` | yes (free; `DEMO_KEY` works for testing) | Picture of the day, title, explanation |
| + | **Open-Meteo Geocoding** `geocoding-api.open-meteo.com/v1/search` | no | City name to lat/lon in the location search box |
| + | **NOAA SWPC** `services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json` | no | Kp index for the aurora screen |
| (check) | **Where The ISS At** `api.wheretheiss.at/v1/satellites/25544` | no | Only used to check that our own SGP4 engine is correct |

**Caching:** every API response is cached in memory with a TTL (weather 30 min, TLEs 6 h, APOD 24 h, Kp 1 h). CelesTrak asks clients not to download the same data more than once every 2 hours, and the NASA key has a rate limit, so this is required.

## 4. Screens

### Screen 1: Tonight's Sky (home)

- **Location picker:** search by city (geocoding API), click on a Leaflet map, or "use my location" (browser geolocation). Stored in `localStorage`.
- **Best hour today:** a big card such as "Best viewing: 23:00, score 87/100".
- **Hourly chart:** bar for each hour from sunset to sunrise, colored by score, with cloud cover overlaid.
- **Planets:** Mercury to Neptune plus the Moon: visible or not, rise/set times, current altitude and direction (e.g. "Jupiter, 34° up, SE, magnitude -2.5").
- **ISS:** next visible pass (start time, max elevation, direction), with a link to screen 2.
- **Starlink:** how many satellites are above the horizon right now and how many are sunlit (actually visible to the eye). Highlight "trains" from recent launches.
- **Sky dome:** a circular canvas chart (horizon = edge, zenith = centre) showing planets, Moon, ISS and Starlink dots in real time.

### Screen 2: ISS Tracker

- World map with the ISS's current position (updates every few seconds) and its ground track for ±1 orbit.
- Table of upcoming passes over the chosen location for the next 3 days: start, max, end time; azimuths; max elevation; visible or not.
- Speed, altitude, period, and "our engine vs. live API" difference in km, to show the engine works.

### Screen 3: NASA Picture of the Day

- Image (or video embed when `media_type == "video"`), title, date, explanation, copyright.
- Date picker to browse older pictures (APOD supports `date=`).

### Screen 4 (the extra): Aurora & Space Weather

- Current and 3-day forecast Kp index from NOAA SWPC.
- From Kp and the user's geomagnetic latitude, a simple "chance of seeing aurora tonight" rating.
- Combined with screen 1's cloud score: "Kp 6 tonight and clear skies at 22:00, worth looking north."

Fits the app's theme, needs no API key, and adds real computation (geomagnetic latitude from the dipole model). Alternatives if you prefer: a meteor shower calendar (static data + radiant altitude computation), or `.ics` export of ISS passes to your calendar.

## 5. Astronomy engine (the C++ core)

All in `src/astro/`, no astronomy library used. That is the main part of the work.

| Module | What it does |
|---|---|
| `time` | UTC to Julian Date, Greenwich/local sidereal time |
| `coords` | Conversions: equatorial (RA/Dec) to horizontal (alt/az); TEME to ECEF to geodetic; observer topocentric vectors |
| `sun_moon` | Sun and Moon positions (low-precision Meeus formulas), Moon phase and illumination, sunrise/sunset and twilight times |
| `planets` | Planet positions from JPL's approximate Keplerian elements (solve Kepler's equation, heliocentric to geocentric to RA/Dec), magnitudes, rise/set |
| `tle` | Parse 3-line TLE text from CelesTrak |
| `sgp4` | SGP4 propagator (following Vallado et al., "Revisiting Spacetrack Report #3", 2006): TLE + time → position/velocity in TEME frame |
| `passes` | Pass prediction: step through time (30 s), find when elevation crosses 0°, refine by bisection to get rise/peak/set; mark pass as *visible* if satellite is sunlit (not in Earth's shadow) and the observer's sun altitude < -6° |
| `sky_quality` | Hourly score 0–100 (see below) |

### Sky visibility score (per hour)

```
if sun altitude > -6°:  score = 0          (too bright)
clouds   = 1 - (1-low)(1-0.8*mid)(1-0.5*high)   (fractions; layers block independently,
                                                 thin high cirrus counts half)
score    = 100 * (1 - clouds)
         - 15  * (1 - visibility/24km, clamped)
         - 10  * (humidity > 85%)
         - 20  * precipitation_probability
         - 25  * moon_illumination * (moon above horizon)
darkness: score × 0.5 at sun -6°, rising linearly to × 1.0 at -18° (astronomical night)
```

(The first draft used a weighted sum `0.5*low + 0.3*mid + 0.2*high`, but that gave a sky fully covered by low cloud 60/100.)

The best hour is the highest-scoring hour between now and the next sunrise. Weights are a starting point and will be tuned.

### ISS engine validation

1. Unit tests against the official SGP4 test vectors (Vallado's `SGP4-VER.TLE` set) to within ~1 m.
2. Live comparison with `wheretheiss.at`: difference should stay under a few km.
3. Spot-check pass times against Heavens-Above for the same location.

## 6. Backend REST API

The C++ server exposes JSON endpoints that the frontend calls:

| Endpoint | Returns |
|---|---|
| `GET /api/geocode?q=Warsaw` | List of matching places with lat/lon |
| `GET /api/sky?lat=&lon=` | Hourly scores, best hour, sunset/sunrise, twilight times, Moon phase |
| `GET /api/planets?lat=&lon=` | Each planet: alt, az, magnitude, rise/set, visible |
| `GET /api/iss/now` | ISS lat, lon, altitude, velocity (from our engine) + API comparison |
| `GET /api/iss/track?minutes=90` | Ground track points |
| `GET /api/iss/passes?lat=&lon=&days=3` | Pass list |
| `GET /api/starlink?lat=&lon=` | Counts, plus alt/az of visible satellites for the sky dome |
| `GET /api/apod?date=` | APOD data |
| `GET /api/aurora?lat=&lon=` | Kp forecast and aurora chance |

Everything else (`/`, `/iss.html`, `/apod.html`, `/aurora.html`, `/css`, `/js`) is served as static files from `web/`.

## 7. Project structure

```
vibe_proj/
├── CMakeLists.txt
├── config.example.json        # NASA API key, port (real config.json is gitignored)
├── src/
│   ├── main.cpp               # server startup, routes
│   ├── http/
│   │   ├── HttpClient.hpp/.cpp   # HTTPS GET wrapper around httplib
│   │   └── Cache.hpp             # TTL cache
│   ├── apis/
│   │   ├── OpenMeteo.hpp/.cpp
│   │   ├── Celestrak.hpp/.cpp
│   │   ├── NasaApod.hpp/.cpp
│   │   ├── Geocoding.hpp/.cpp
│   │   └── Swpc.hpp/.cpp
│   ├── astro/
│   │   ├── time.hpp/.cpp
│   │   ├── coords.hpp/.cpp
│   │   ├── sun_moon.hpp/.cpp
│   │   ├── planets.hpp/.cpp
│   │   ├── tle.hpp/.cpp
│   │   ├── sgp4.hpp/.cpp
│   │   └── passes.hpp/.cpp
│   └── services/
│       ├── SkyQuality.hpp/.cpp   # hourly score + the /api/sky report
│       ├── Planets.hpp/.cpp      # the /api/planets report
│       └── Aurora.hpp/.cpp
├── web/
│   ├── index.html             # Tonight's Sky
│   ├── iss.html
│   ├── apod.html
│   ├── aurora.html
│   ├── css/style.css
│   └── js/{common,location,sky,skydome,iss,apod,aurora}.js   # location.js: shared picker
└── tests/
    ├── test_time.cpp
    ├── test_sun_moon.cpp
    ├── test_planets.cpp
    ├── test_sgp4.cpp
    └── test_sky_quality.cpp
```

## 8. Milestones

| # | Milestone | Done when |
|---|---|---|
| 1 | **Skeleton** | CMake builds; server on `localhost:8080` serves a "hello" page and `/api/health` |
| 2 | **API layer** | HttpClient + Cache; each API client fetches and parses its data; config file with NASA key |
| 3 | **APOD screen** | Screen 3 works end to end (easiest screen, proves the whole pipeline) |
| 4 | **Time, coords, Sun/Moon** | Sunrise/sunset and Moon phase match timeanddate.com within ~2 min |
| 5 | **Sky quality + screen 1 (part 1)** | Location picker, hourly chart, best-hour card |
| 6 | **Planets** | Planet alt/az match Stellarium within ~1° |
| 7 | **SGP4 engine** | Passes Vallado test vectors; matches wheretheiss.at within a few km |
| 8 | **ISS screen + passes** | Map, ground track, pass table; pass times match Heavens-Above within ~1 min |
| 9 | **Starlink + sky dome** | Starlink counts and sky dome on screen 1 (all ~8–10k satellites propagated per request, should take well under a second in C++) |
| 10 | **Aurora screen** | Kp chart and aurora rating |
| 11 | **Polish** | Error states (API down, no location), loading spinners, mobile layout, README with screenshots |

Milestones 3, 4 and 7 can be developed in parallel since they don't depend on each other.

**Progress:** all 11 milestones done (22 October 2026). See README.md for the build, the API and the accuracy table. Changes from the original plan:
- Clouds are applied everywhere: planet "tonight" windows, ISS passes (sky column), Starlink "visible now" and the aurora rating, not just the hourly score.
- CelesTrak was unreachable from the development network (connection timeouts). TLEs are cached on disk, and the ISS falls back to SatNOGS (Space-Track data). Starlink has no fallback and says so in its card.
- Mercury and Venus magnitudes use Mallama & Hilton (2018) instead of Meeus' older fits.
- Locations can be shared as links (`?lat=&lon=&name=`); the location's time zone carries over between screens.

## 9. Risks

- **SGP4 is the hardest part.** Follow Vallado's paper and reference code closely and test against its vectors early. Fallback: if time runs out, use a simpler two-body Kepler propagator (accurate for a few hours only), and say so in the docs.
- **NASA's APOD API is partly broken** (found in milestone 3): APOD moved to science.nasa.gov and the API now returns a placeholder image and another day's explanation. The backend detects the placeholder and reads the title, image, explanation and credit from the article page's HTML instead. A few recent days can't be found that way; the screen then links to NASA's page.
- **NASA `DEMO_KEY` limit** is 30 requests/hour per IP. Get a free personal key at api.nasa.gov and rely on the 24 h cache.
- **CelesTrak blocks clients** that download too often, so the 6 h TLE cache must work before testing Starlink in a loop.
- **HTTPS in httplib** requires OpenSSL to be found by CMake; on macOS set `OPENSSL_ROOT_DIR=$(brew --prefix openssl)`.

## 10. Decisions

- **Runs locally:** `./skywatch` starts the server, then open `http://localhost:8080`. No deployment, no Docker.
- **JavaScript is allowed** in the browser for maps, charts and live updates. All data fetching and astronomy math stays in C++.
- **UI language:** English.
