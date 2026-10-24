"""The /api/planets response."""

import math
from collections.abc import Callable
from typing import NamedTuple

from skywatch.apis.open_meteo import Forecast, weather_at
from skywatch.astro.coords import Horizontal, compass_point, deg
from skywatch.astro.planets import PLANET_RISE_SET_ALT_DEG, PLANETS, planet_horizontal, planet_position
from skywatch.astro.sun_moon import (
    RISE_SET_ALT_DEG,
    find_crossings,
    first_crossing_after,
    moon_horizontal,
    moon_phase,
    moon_position,
    sun_horizontal,
    tonight,
)
from skywatch.astro.time import jd_from_unix, unix_from_jd
from skywatch.services.json_util import iround, round1, round3, sky_position, unix_or_none
from skywatch.services.sky_quality import MAX_CLOUD_BLOCKING, clamp01, cloud_blocking

_MIN_ALT_DEG = 10  # lower than this, haze and buildings usually hide things
_DARK_SUN_ALT_DEG = -6  # end of civil twilight: bright planets show
_NAKED_EYE_MAG = 6  # faintest magnitude visible without optics
_SAMPLE_DAYS = 5.0 / 1440


def _moon_magnitude(illumination: float) -> float:
    """Moon magnitude from its phase angle (Allen, Astrophysical Quantities)."""
    i = deg(math.acos(max(-1.0, min(1.0, 2 * illumination - 1))))
    return -12.73 + 0.026 * i + 4e-9 * i**4


class BodyVisibility(NamedTuple):
    score: int
    limit: str | None


def body_visibility(
    alt_deg: float, magnitude: float, sun_alt_deg: float, cloud_blocking_: float, moon_glow: float
) -> BodyVisibility:
    """How well a body can be seen at one moment: 0 (not at all) to 100 (high
    in a dark, clear sky), and the factor that holds it back most ("too_low",
    "too_bright", "clouds", "moonlight"), or None when nothing does. moon_glow
    is the Moon's illumination while it is up (0 when down); it only matters
    for faint bodies."""
    # Low down, the light crosses more air: dimmer and blurrier. Full marks from 40° up.
    altitude = 0.0 if alt_deg < _MIN_ALT_DEG else 0.4 + 0.6 * clamp01((alt_deg - _MIN_ALT_DEG) / 30)
    # Brighter bodies show earlier in twilight: Venus with the Sun 3° down, a
    # magnitude 2 planet only at -18°. The factor fades in over 6° around that point.
    need_sun_alt = max(-18.0, min(-3.0, -3 - 2.5 * (magnitude + 4)))
    darkness = clamp01((need_sun_alt + 3 - sun_alt_deg) / 6)
    # Like everywhere else in the app, only a mostly clear sky counts.
    clouds = 0.0 if cloud_blocking_ >= MAX_CLOUD_BLOCKING else 1 - clamp01(cloud_blocking_)
    # Moonlight drowns faint bodies (magnitude 3 and fainter), not bright planets.
    moonlight = 1 - 0.5 * clamp01(moon_glow) * clamp01((magnitude - 3) / 3)

    score = 100 * altitude * darkness * clouds * moonlight
    # min() keeps the first of equal factors, like std::min_element.
    worst = min(
        ((altitude, "too_low"), (darkness, "too_bright"), (clouds, "clouds"), (moonlight, "moonlight")),
        key=lambda f: f[0],
    )
    return BodyVisibility(iround(score), worst[1] if worst[0] < 0.9 else None)


class _Hour(NamedTuple):
    unix: float
    jd: float
    sun_alt: float
    blocking: float
    moon_glow: float
    past: bool


def planets_report(lat: float, lon: float, now_unix: float, forecast: Forecast | None) -> dict:
    """The Moon and the seven planets, where each is now, when it next rises and
    sets, and the stretches of tonight when it is high in a dark, mostly clear
    sky, plus an hourly visibility score from sunset to sunrise (the same hours
    as /api/sky) and the best hour still ahead. Without a forecast (weather API
    down) clouds are ignored."""
    jd_now = jd_from_unix(now_unix)
    night = tonight(jd_now, lat, lon)

    def clear(jd: float) -> bool:
        # Hours the forecast doesn't cover count as clear rather than hiding everything.
        w = weather_at(forecast, unix_from_jd(jd)) if forecast else None
        return w is None or cloud_blocking(w) < MAX_CLOUD_BLOCKING

    # The rest of tonight, sampled every 5 minutes. Darkness and clouds are the
    # same for every body, so they are worked out once.
    dark_times: list[tuple[float, bool]] = []
    # Whole hours from sunset to sunrise, matching the /api/sky timeline. What
    # the Sun, clouds and Moon do each hour is the same for every body.
    hours: list[_Hour] = []
    if night.polar != "day":
        jd = max(night.start, jd_now)
        while jd <= night.end:
            if sun_horizontal(jd, lat, lon).alt_deg <= _DARK_SUN_ALT_DEG:
                dark_times.append((jd, clear(jd)))
            jd += _SAMPLE_DAYS

        end_unix = unix_from_jd(night.end)
        t = math.floor(unix_from_jd(night.start) / 3600) * 3600
        while t <= end_unix:
            jd = jd_from_unix(t)
            w = weather_at(forecast, t) if forecast else None
            moon_glow = moon_phase(jd).illumination if moon_horizontal(jd, lat, lon).alt_deg > 0 else 0.0
            hours.append(
                _Hour(t, jd, sun_horizontal(jd, lat, lon).alt_deg, cloud_blocking(w) if w else 0.0, moon_glow, t + 3600 <= now_unix)
            )
            t += 3600

    dark_now = sun_horizontal(jd_now, lat, lon).alt_deg <= _DARK_SUN_ALT_DEG
    clear_now = clear(jd_now)

    def describe(
        name: str, horizontal: Callable[[float], Horizontal], rise_set_alt_deg: float, mag: float, is_moon: bool
    ) -> dict:
        def alt(jd: float) -> float:
            return horizontal(jd).alt_deg

        xs = find_crossings(alt, jd_now, jd_now + 1.2, rise_set_alt_deg)
        now = horizontal(jd_now)

        # Clear stretches as [from, to] pairs; a cloudy hour splits them.
        windows = []
        high_tonight = False
        from_ = to = None
        for jd, is_clear in dark_times:
            high = alt(jd) >= _MIN_ALT_DEG
            high_tonight = high_tonight or high
            if high and is_clear:
                if from_ is None:
                    from_ = jd
                to = jd
            elif from_ is not None:
                windows.append({"from": unix_or_none(from_), "to": unix_or_none(to)})
                from_ = None
        if from_ is not None:
            windows.append({"from": unix_or_none(from_), "to": unix_or_none(to)})

        hourly = []
        best = None
        for h in hours:
            pos = horizontal(h.jd)
            v = body_visibility(pos.alt_deg, mag, h.sun_alt, h.blocking, 0.0 if is_moon else h.moon_glow)
            hourly.append(
                {
                    "time": iround(h.unix),
                    "score": v.score,
                    "alt": round1(pos.alt_deg),
                    "direction": compass_point(pos.az_deg),
                    "limit": v.limit,
                }
            )
            # Ties go to the earlier hour.
            if not h.past and v.score > 0 and (best is None or v.score > best["score"]):
                best = hourly[-1]

        naked_eye = mag <= _NAKED_EYE_MAG
        return {
            "name": name,
            "position": sky_position(now),
            "magnitude": round1(mag),
            "naked_eye": naked_eye,
            "up": now.alt_deg > 0,
            "visible_now": dark_now and clear_now and naked_eye and now.alt_deg >= _MIN_ALT_DEG,
            "rise": unix_or_none(first_crossing_after(xs, jd_now, True)),
            "set": unix_or_none(first_crossing_after(xs, jd_now, False)),
            # high_tonight without any windows means clouds are in the way.
            "high_tonight": high_tonight,
            "tonight": windows,
            "hours": hourly,
            "best": best,
        }

    phase = moon_phase(jd_now)
    moon = describe(
        "Moon",
        lambda jd: moon_horizontal(jd, lat, lon),
        RISE_SET_ALT_DEG,
        _moon_magnitude(phase.illumination),
        True,
    )
    moon["distance_km"] = iround(moon_position(jd_now).distance_km)
    moon["illumination"] = round3(phase.illumination)
    bodies = [moon]

    for planet in PLANETS:
        pos = planet_position(planet, jd_now)
        body = describe(
            planet,
            lambda jd, planet=planet: planet_horizontal(planet, jd, lat, lon),
            PLANET_RISE_SET_ALT_DEG,
            pos.magnitude,
            False,
        )
        body["distance_au"] = round3(pos.distance_au)
        body["elongation"] = round1(pos.elongation_deg)
        bodies.append(body)

    return {"now": iround(now_unix), "weather": forecast is not None, "bodies": bodies}
