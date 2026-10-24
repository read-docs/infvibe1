"""How good the sky is for stargazing, hour by hour."""

import math

from skywatch.apis.open_meteo import Forecast, HourlyWeather
from skywatch.astro.sun_moon import (
    RISE_SET_ALT_DEG,
    find_crossings,
    first_crossing_after,
    last_crossing_before,
    moon_horizontal,
    moon_phase,
    sun_horizontal,
    tonight,
)
from skywatch.astro.time import jd_from_unix, unix_from_jd
from skywatch.services.json_util import iround, round1, round3, round_half_away, sky_position, unix_or_none

# Cloud blocking above which the sky counts as clouded out, even for bright
# planets or aurora.
MAX_CLOUD_BLOCKING = 0.5


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def cloud_blocking(w: HourlyWeather) -> float:
    """Fraction of the sky (0..1) blocked by clouds. Each layer hides what is
    behind it independently; high clouds are mostly thin cirrus, so they count less."""
    clear = (
        (1 - clamp01(w.cloud_low / 100))
        * (1 - 0.8 * clamp01(w.cloud_mid / 100))
        * (1 - 0.5 * clamp01(w.cloud_high / 100))
    )
    return 1 - clear


def sky_condition(blocking: float) -> str:
    """Sky condition for a cloud blocking fraction: "clear", "mostly_clear"
    (both good for viewing), "cloudy" or "overcast"."""
    if blocking < 0.15:
        return "clear"
    if blocking < MAX_CLOUD_BLOCKING:
        return "mostly_clear"
    if blocking < 0.85:
        return "cloudy"
    return "overcast"


def hour_score(w: HourlyWeather, sun_alt_deg: float, moon_alt_deg: float, moon_illumination: float) -> int:
    """How good one hour is for stargazing, 0 (nothing to see) to 100 (perfect)."""
    if sun_alt_deg > -6:
        return 0  # civil twilight or daylight: too bright

    score = 100 * (1 - cloud_blocking(w))
    score -= 15 * (1 - clamp01(w.visibility_m / 24000))  # haze
    if w.humidity > 85:
        score -= 10  # dew and mist
    score -= 20 * clamp01(w.precip_probability / 100)
    if moon_alt_deg > 0:
        score -= 25 * moon_illumination  # moonlight washes out faint stars

    # Faint objects need astronomical night (Sun below -18°); in nautical and
    # astronomical twilight only the bright planets and stars show, so the score is scaled down.
    darkness = clamp01((-6 - sun_alt_deg) / 12)
    score *= 0.5 + 0.5 * darkness
    return iround(max(0.0, min(100.0, score)))


def sky_report(forecast: Forecast, lat: float, lon: float, now_unix: float) -> dict:
    """The /api/sky response: Sun and Moon now, tonight's twilight times, and an
    hourly score from sunset to sunrise with the best hour still ahead of
    now_unix, and a whole-night rating: the average score over the dark hours
    (Sun below -6°)."""
    jd_now = jd_from_unix(now_unix)

    def sun_alt(jd: float) -> float:
        return sun_horizontal(jd, lat, lon).alt_deg

    def moon_alt(jd: float) -> float:
        return moon_horizontal(jd, lat, lon).alt_deg

    night = tonight(jd_now, lat, lon)
    start, end = night.start, night.end

    twilight = {}
    for name, alt_deg in (("civil", -6), ("nautical", -12), ("astronomical", -18)):
        xs = find_crossings(sun_alt, start, end, alt_deg)
        twilight[name] = {
            "dusk": unix_or_none(first_crossing_after(xs, start, False)),
            "dawn": unix_or_none(last_crossing_before(xs, end, True)),
        }

    hours = []
    best = None
    dark_hours = clear_hours = score_sum = 0
    first_hour = math.floor(unix_from_jd(start) / 3600) * 3600
    end_unix = unix_from_jd(end)
    for w in forecast.hours:
        if w.time < first_hour or w.time > end_unix:
            continue
        jd = jd_from_unix(w.time)
        s_alt = sun_alt(jd)
        m_alt = moon_alt(jd)
        score = hour_score(w, s_alt, m_alt, moon_phase(jd).illumination)
        past = w.time + 3600 <= now_unix
        blocking = cloud_blocking(w)
        dark = s_alt <= -6
        if dark:
            dark_hours += 1
            score_sum += score
            if blocking < MAX_CLOUD_BLOCKING:
                clear_hours += 1
        hours.append(
            {
                "time": iround(w.time),
                "score": score,
                "past": past,
                "dark": dark,
                "sky": sky_condition(blocking),
                "cloud_blocking": iround(blocking * 100),
                "cloud_cover": w.cloud_cover,
                "cloud_low": w.cloud_low,
                "cloud_mid": w.cloud_mid,
                "cloud_high": w.cloud_high,
                "visibility_km": round_half_away(w.visibility_m / 100) / 10,
                "humidity": w.humidity,
                "precip_probability": w.precip_probability,
                "sun_alt": round1(s_alt),
                "moon_alt": round1(m_alt),
            }
        )
        # Ties go to the earlier hour.
        if not past and score > 0 and (best is None or score > best["score"]):
            best = {"time": iround(w.time), "score": score}

    moon_xs = find_crossings(moon_alt, jd_now, jd_now + 1.2, RISE_SET_ALT_DEG)
    phase = moon_phase(jd_now)

    return {
        "location": {
            "lat": lat,
            "lon": lon,
            "timezone": forecast.timezone,
            "utc_offset_seconds": forecast.utc_offset_seconds,
        },
        "now": iround(now_unix),
        "sun": sky_position(sun_horizontal(jd_now, lat, lon)),
        "moon": {
            "position": sky_position(moon_horizontal(jd_now, lat, lon)),
            "illumination": round3(phase.illumination),
            "phase": phase.name,
            "waxing": phase.waxing,
            "rise": unix_or_none(first_crossing_after(moon_xs, jd_now, True)),
            "set": unix_or_none(first_crossing_after(moon_xs, jd_now, False)),
        },
        "night": {
            "sunset": None if night.polar else unix_or_none(start),
            "sunrise": None if night.polar else unix_or_none(end),
            "polar": night.polar,
            "twilight": twilight,
        },
        "hours": hours,
        "best": best,
        "night_quality": {
            "percent": iround(score_sum / dark_hours) if dark_hours else None,
            "dark_hours": dark_hours,
            "clear_hours": clear_hours,
        },
    }
