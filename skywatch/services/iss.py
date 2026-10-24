"""JSON for the ISS endpoints, all computed with our own SGP4 engine."""

from skywatch.apis.celestrak import SatelliteSet
from skywatch.apis.open_meteo import Forecast, weather_at
from skywatch.apis.where_the_iss import LiveIssPosition
from skywatch.astro.coords import Geodetic, compass_point, ecef_to_geodetic, geodetic_to_ecef, norm, sub, teme_to_ecef
from skywatch.astro.passes import ISS_STD_MAGNITUDE, PassPoint, find_passes, subpoint, view_satellite
from skywatch.astro.sgp4 import Sgp4
from skywatch.astro.time import jd_from_unix, unix_from_jd
from skywatch.services.json_util import iround, round1, round3, round_half_away, sky_position, unix_or_none
from skywatch.services.sky_quality import MAX_CLOUD_BLOCKING, cloud_blocking


def _pass_point(p: PassPoint) -> dict:
    return {
        "time": iround(unix_from_jd(p.jd)),
        "alt": round1(p.alt_deg),
        "az": round1(p.az_deg),
        "direction": compass_point(p.az_deg),
    }


def iss_now(iss: SatelliteSet, now_unix: float, observer: Geodetic | None) -> dict:
    """Where the ISS is now; with an observer, also where to look for it."""
    sat = iss.satellites[0]
    jd = jd_from_unix(now_unix)
    # Any observer works for the subpoint; the look angles are only reported when one was given.
    v = view_satellite(sat, jd, observer or Geodetic(0, 0, 0), ISS_STD_MAGNITUDE)
    out = {
        "time": iround(now_unix),
        "lat": round_half_away(v.subpoint.lat_deg * 1e4) / 1e4,
        "lon": round_half_away(v.subpoint.lon_deg * 1e4) / 1e4,
        "alt_km": round1(v.subpoint.alt_km),
        "speed_kms": round3(v.speed_km_s),
        "period_min": round1(sat.period_minutes()),
        "sunlit": v.sunlit,
        "tle": {
            "epoch": unix_or_none(sat.tle.epoch_jd),
            "source": iss.source,
            "age_hours": round1((jd - sat.tle.epoch_jd) * 24),
        },
    }
    if observer is not None:
        out["look"] = sky_position(v.look.h)
        out["look"]["range_km"] = iround(v.look.range_km)
    return out


def iss_check(sat: Sgp4, live: LiveIssPosition) -> dict:
    """Our position at the live API's timestamp next to the live one, and the
    distance between them."""
    jd = jd_from_unix(live.unix_time)
    ours = teme_to_ecef(sat.at(jd).r, jd)
    theirs = geodetic_to_ecef(Geodetic(live.lat_deg, live.lon_deg, live.alt_km))
    g = ecef_to_geodetic(ours)
    return {
        "source": "wheretheiss.at",
        "time": iround(live.unix_time),
        "live": {"lat": live.lat_deg, "lon": live.lon_deg, "alt_km": round1(live.alt_km)},
        "ours": {"lat": g.lat_deg, "lon": g.lon_deg, "alt_km": round1(g.alt_km)},
        "difference_km": round_half_away(norm(sub(ours, theirs)) * 100) / 100,
    }


def iss_track(sat: Sgp4, now_unix: float, minutes: float) -> dict:
    """Ground track from minutes before to minutes after now, every 30 seconds."""
    points = []
    t = now_unix - minutes * 60
    while t <= now_unix + minutes * 60:
        g = subpoint(sat, jd_from_unix(t))
        points.append(
            {
                "time": iround(t),
                "lat": round_half_away(g.lat_deg * 1e3) / 1e3,
                "lon": round_half_away(g.lon_deg * 1e3) / 1e3,
            }
        )
        t += 30
    return {"now": iround(now_unix), "points": points}


def iss_passes(sat: Sgp4, observer: Geodetic, now_unix: float, days: float, forecast: Forecast | None) -> dict:
    """Passes over the observer in the next `days` days. With a forecast, each
    visible pass also gets the cloud cover and whether the sky is clear enough."""
    jd = jd_from_unix(now_unix)
    out = []
    for p in find_passes(sat, observer, jd, jd + days, ISS_STD_MAGNITUDE):
        item = {
            "rise": _pass_point(p.rise),
            "peak": _pass_point(p.peak),
            "set": _pass_point(p.set),
            "visible": p.visible,
        }
        if p.visible_start is not None:
            item["visible_part"] = {
                "start": _pass_point(p.visible_start),
                "end": _pass_point(p.visible_end),
                "max_alt": round1(p.visible_max_alt_deg),
                "magnitude": round1(p.brightest_magnitude),
            }
            w = weather_at(forecast, unix_from_jd(p.visible_start.jd)) if forecast else None
            if w is not None:
                blocking = cloud_blocking(w)
                item["cloud"] = iround(blocking * 100)
                item["clear"] = blocking < MAX_CLOUD_BLOCKING
        out.append(item)
    return {"now": iround(now_unix), "passes": out}
