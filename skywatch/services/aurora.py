"""The /api/aurora response."""

import math

from skywatch.apis.open_meteo import Forecast, weather_at
from skywatch.apis.swpc import KpData
from skywatch.astro.coords import cos_deg, deg, sin_deg
from skywatch.astro.sun_moon import sun_horizontal, tonight
from skywatch.astro.time import jd_from_unix, unix_from_jd
from skywatch.services.json_util import iround, round1, round2, round_half_away
from skywatch.services.sky_quality import MAX_CLOUD_BLOCKING, cloud_blocking

_POLE_LAT, _POLE_LON = 80.8, -72.8
# A rule of thumb fitted to NOAA's aurora "view line": at Kp 0 the oval's edge
# sits near 67° geomagnetic latitude and moves ~2° towards the equator per Kp
# step; from the ground the aurora shows low on the horizon ~7° beyond that.
_OVAL_EDGE_AT_KP0, _OVAL_DEG_PER_KP, _HORIZON_REACH, _CAMERA_REACH = 67, 2, 7, 10
_AURORA_DARK_SUN_ALT_DEG = -12  # aurora is faint: needs nautical darkness

_RANK = {"overhead": 3, "horizon": 2, "camera": 1}


def _kp_at(kp: KpData, t: float) -> float:
    """Kp of the 3-hour interval containing t, or -1."""
    for p in kp.three_hour:
        if p.time <= t < p.time + 3 * 3600:
            return p.kp
    return -1


def geomagnetic_latitude(lat: float, lon: float) -> float:
    """Geomagnetic latitude in the centred dipole model of Earth's magnetic
    field (pole at 80.8°N, 72.8°W, IGRF 2025). Aurora follows this, not
    geographic latitude."""
    s = sin_deg(lat) * sin_deg(_POLE_LAT) + cos_deg(lat) * cos_deg(_POLE_LAT) * cos_deg(lon - _POLE_LON)
    return deg(math.asin(max(-1.0, min(1.0, s))))


def aurora_chance(kp: float, geomag_lat_deg: float) -> str:
    """How likely aurora is for a given Kp at a geomagnetic latitude:
    "overhead", "horizon" (low towards the pole), "camera" (only long exposures
    might catch it) or "none"."""
    if kp < 0:
        return "none"
    edge = _OVAL_EDGE_AT_KP0 - _OVAL_DEG_PER_KP * kp
    m = abs(geomag_lat_deg)
    if m >= edge:
        return "overhead"
    if m >= edge - _HORIZON_REACH:
        return "horizon"
    if m >= edge - _CAMERA_REACH:
        return "camera"
    return "none"


def aurora_report(kp: KpData, forecast: Forecast | None, lat: float, lon: float, now_unix: float) -> dict:
    """Kp now and forecast, what Kp this location needs, and tonight's hours
    combining the Kp forecast, darkness and clouds."""
    mlat = geomagnetic_latitude(lat, lon)
    m = abs(mlat)

    def needed(reach: float) -> float:
        # Inverting the rule: the Kp at which the oval's edge (or the horizon view) reaches us.
        return max(0.0, min(9.0, (_OVAL_EDGE_AT_KP0 - reach - m) / _OVAL_DEG_PER_KP))

    series = [
        {"time": iround(p.time), "kp": round2(p.kp), "kind": p.kind, "chance": aurora_chance(p.kp, mlat)}
        for p in kp.three_hour
        if p.time >= now_unix - 2 * 86400  # two days of history is plenty
    ]

    # Tonight, hour by hour.
    jd_now = jd_from_unix(now_unix)
    night = tonight(jd_now, lat, lon)
    hours = []
    best = None
    best_rank = -1
    best_cloud = 2.0
    max_kp = -1.0
    if night.polar != "day":
        t = math.floor(unix_from_jd(max(night.start, jd_now)) / 3600) * 3600
        end_unix = unix_from_jd(night.end)
        while t <= end_unix:
            sun_alt = sun_horizontal(jd_from_unix(t + 1800), lat, lon).alt_deg
            if sun_alt <= _AURORA_DARK_SUN_ALT_DEG:
                k = _kp_at(kp, t + 1800)
                max_kp = max(max_kp, k)
                chance = aurora_chance(k, mlat)
                w = weather_at(forecast, t + 1800) if forecast else None
                cloud = cloud_blocking(w) if w else -1.0
                hours.append(
                    {
                        "time": iround(t),
                        "kp": round2(k),
                        "chance": chance,
                        "cloud": round_half_away(cloud * 100) if w else None,
                    }
                )
                # Best: the strongest chance, then the clearest sky.
                r = _RANK.get(chance, 0)
                c = cloud if w else 0.5
                if r > best_rank or (r == best_rank and c < best_cloud):
                    best_rank, best_cloud, best = r, c, hours[-1]
            t += 3600

    # One overall verdict for tonight.
    if not hours:
        verdict = "no_darkness"
    elif best_rank >= 2 and (forecast is None or best_cloud < MAX_CLOUD_BLOCKING):
        verdict = "go"
    elif best_rank >= 2:
        verdict = "cloudy"
    elif best_rank == 1:
        verdict = "camera"
    else:
        verdict = "unlikely"

    return {
        "location": {
            "lat": lat,
            "lon": lon,
            "geomagnetic_lat": round1(mlat),
            "look_towards": "north" if mlat >= 0 else "south",
        },
        "kp_needed": {"overhead": round1(needed(0)), "horizon": round1(needed(_HORIZON_REACH))},
        "now": {
            "kp": round2(kp.current) if kp.current is not None else None,
            "chance": aurora_chance(kp.current if kp.current is not None else _kp_at(kp, now_unix), mlat),
            "dark": sun_horizontal(jd_now, lat, lon).alt_deg <= _AURORA_DARK_SUN_ALT_DEG,
        },
        "forecast": series,
        "tonight": {
            "hours": hours,
            "best": best,
            "max_kp": round2(max_kp),
            "verdict": verdict,
            "weather": forecast is not None,
        },
    }
