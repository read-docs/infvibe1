"""The /api/starlink response."""

from dataclasses import dataclass

from skywatch.apis.celestrak import SatelliteSet
from skywatch.apis.open_meteo import Forecast, weather_at
from skywatch.astro.coords import Geodetic, look_angles, norm, teme_to_ecef
from skywatch.astro.passes import STARLINK_STD_MAGNITUDE, view_satellite
from skywatch.astro.sgp4 import Sgp4Error
from skywatch.astro.sun_moon import sun_horizontal
from skywatch.astro.time import jd_from_unix
from skywatch.services.json_util import iround, round1
from skywatch.services.sky_quality import MAX_CLOUD_BLOCKING, cloud_blocking

_MIN_VISIBLE_ALT_DEG = 10
_DARK_SUN_ALT_DEG = -6
_NAKED_EYE_MAG = 6
_EARTH_RADIUS_KM = 6378.137
# Starlinks are released around 300 km and climb to ~550 km over a few weeks;
# while still low they fly in a bright line, the "train".
_TRAIN_MAX_ALT_KM = 450
_RECENT_LAUNCHES = 3


def _launch_of(designator: str) -> str:
    """"21082Q" -> "2021-082" (year, launch number of that year; the letter is the piece)."""
    if len(designator) < 5:
        return ""
    try:
        yy = int(designator[:2])
    except ValueError:
        return ""
    return f"{2000 + yy if yy < 57 else 1900 + yy}-{designator[2:5]}"


@dataclass
class _LaunchStats:
    satellites: int = 0
    above_horizon: int = 0
    visible: int = 0
    alt_sum_km: float = 0.0


def starlink_report(
    sats: SatelliteSet, lat: float, lon: float, now_unix: float, forecast: Forecast | None = None
) -> dict:
    """How many Starlink satellites are above the observer right now, how many
    of them can actually be seen (sunlit in a dark sky), the most recent
    launches, and the position of each one above the horizon. With a forecast,
    an overcast sky means none of them count as visible."""
    jd = jd_from_unix(now_unix)
    observer = Geodetic(lat, lon, 0)
    dark = sun_horizontal(jd, lat, lon).alt_deg <= _DARK_SUN_ALT_DEG
    w = weather_at(forecast, now_unix) if forecast else None
    cloudy = w is not None and cloud_blocking(w) >= MAX_CLOUD_BLOCKING

    launches: dict[str, _LaunchStats] = {}
    above = []
    total = above_horizon = sunlit_above = visible = 0

    for sat in sats.satellites:
        try:
            state = sat.at(jd)
        except Sgp4Error:
            continue  # decayed since its TLE was published
        total += 1
        launch = _launch_of(sat.tle.intl_designator)
        ls = launches.setdefault(launch, _LaunchStats())
        ls.satellites += 1
        ls.alt_sum_km += norm(state.r) - _EARTH_RADIUS_KM

        look = look_angles(teme_to_ecef(state.r, jd), observer)
        if look.h.alt_deg <= 0:
            continue

        v = view_satellite(sat, jd, observer, STARLINK_STD_MAGNITUDE)
        is_visible = (
            dark
            and not cloudy
            and v.sunlit
            and look.h.alt_deg >= _MIN_VISIBLE_ALT_DEG
            and v.magnitude <= _NAKED_EYE_MAG
        )
        above_horizon += 1
        ls.above_horizon += 1
        if v.sunlit:
            sunlit_above += 1
        if is_visible:
            visible += 1
            ls.visible += 1
        above.append(
            {
                "name": sat.tle.name,
                "launch": launch,
                "alt": round1(look.h.alt_deg),
                "az": round1(look.h.az_deg),
                "sunlit": v.sunlit,
                "visible": is_visible,
                "magnitude": round1(v.magnitude),
            }
        )

    # The newest launches, by year then launch number.
    names = sorted((name for name in launches if name), reverse=True)
    recent = []
    for name in names[:_RECENT_LAUNCHES]:
        ls = launches[name]
        mean_alt = ls.alt_sum_km / ls.satellites
        recent.append(
            {
                "launch": name,
                "satellites": ls.satellites,
                "mean_alt_km": iround(mean_alt),
                "above_horizon": ls.above_horizon,
                "visible": ls.visible,
                "train": mean_alt < _TRAIN_MAX_ALT_KM,
            }
        )

    return {
        "now": iround(now_unix),
        "tle": {"source": sats.source, "fetched": iround(sats.fetched_unix)},
        "sky_dark": dark,
        "cloudy": cloudy,
        "counts": {
            "total": total,
            "above_horizon": above_horizon,
            "sunlit_above": sunlit_above,
            "visible": visible,
        },
        "recent_launches": recent,
        "satellites": above,
    }
