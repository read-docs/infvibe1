"""Low-precision Sun and Moon positions after Meeus, "Astronomical Algorithms"
(2nd ed.), chapters 25, 47 and 48. Accurate to about 0.01° (Sun) and a few
arcminutes (Moon), which keeps rise/set times within a minute or two."""

import math
from collections.abc import Callable
from typing import NamedTuple

from skywatch.astro.coords import (
    Ecliptic,
    Equatorial,
    Horizontal,
    cos_deg,
    deg,
    ecliptic_to_equatorial,
    equatorial_to_horizontal,
    norm_deg,
    obliquity_deg,
    sin_deg,
)
from skywatch.astro.time import centuries_since_j2000, lmst_deg

# Altitude of the Sun's centre at sunrise/sunset: refraction (34') plus the
# Sun's radius (16'). The Moon's radius is about the same, so moonrise uses it too.
RISE_SET_ALT_DEG = -0.833

_EARTH_RADIUS_KM = 6378.14
_AU_KM = 149597870.7


def _node_deg(t: float) -> float:
    """Longitude of the Moon's ascending node, used for the nutation corrections."""
    return 125.04 - 1934.136 * t


def _sun_terms(t: float) -> tuple[float, float, float]:
    """(true longitude, true anomaly, eccentricity)"""
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t * t) * sin_deg(m)
        + (0.019993 - 0.000101 * t) * sin_deg(2 * m)
        + 0.000289 * sin_deg(3 * m)
    )
    ecc = 0.016708634 - 0.000042037 * t - 0.0000001267 * t * t
    return norm_deg(l0 + c), m + c, ecc


def _apparent_obliquity_deg(jd: float) -> float:
    """Obliquity including the main nutation term, for apparent positions."""
    return obliquity_deg(jd) + 0.00256 * cos_deg(_node_deg(centuries_since_j2000(jd)))


# Periodic terms for the Moon's longitude and distance (Meeus table 47.A),
# truncated to coefficients above 0.002°: multiples of D, M, M', F, then
# Σl in 1e-6 degrees and Σr in 1e-3 km.
_MOON_LON_DIST = (
    (0, 0, 1, 0, 6288774, -20905355), (2, 0, -1, 0, 1274027, -3699111),
    (2, 0, 0, 0, 658314, -2955968), (0, 0, 2, 0, 213618, -569925),
    (0, 1, 0, 0, -185116, 48888), (0, 0, 0, 2, -114332, -3149),
    (2, 0, -2, 0, 58793, 246158), (2, -1, -1, 0, 57066, -152138),
    (2, 0, 1, 0, 53322, -170733), (2, -1, 0, 0, 45758, -204586),
    (0, 1, -1, 0, -40923, -129620), (1, 0, 0, 0, -34720, 108743),
    (0, 1, 1, 0, -30383, 104755), (2, 0, 0, -2, 15327, 10321),
    (0, 0, 1, 2, -12528, 0), (0, 0, 1, -2, 10980, 79661),
    (4, 0, -1, 0, 10675, -34782), (0, 0, 3, 0, 10034, -23210),
    (4, 0, -2, 0, 8548, -21636), (2, 1, -1, 0, -7888, 24208),
    (2, 1, 0, 0, -6766, 30824), (1, 0, -1, 0, -5163, -8379),
    (1, 1, 0, 0, 4987, -16675), (2, -1, 1, 0, 4036, -12831),
    (2, 0, 2, 0, 3994, -10445), (4, 0, 0, 0, 3861, -11650),
    (2, 0, -3, 0, 3665, 14403), (0, 1, -2, 0, -2689, -7003),
    (2, 0, -1, 2, -2602, 0), (2, -1, -2, 0, 2390, 10056),
    (1, 0, 1, 0, -2348, 6322), (2, -2, 0, 0, 2236, -9884),
)  # fmt: skip

# Periodic terms for the Moon's latitude (Meeus table 47.B), truncated the same way.
_MOON_LAT = (
    (0, 0, 0, 1, 5128122), (0, 0, 1, 1, 280602), (0, 0, 1, -1, 277693), (2, 0, 0, -1, 173237),
    (2, 0, -1, 1, 55413), (2, 0, -1, -1, 46271), (2, 0, 0, 1, 32573), (0, 0, 2, 1, 17198),
    (2, 0, 1, -1, 9266), (0, 0, 2, -1, 8822), (2, -1, 0, -1, 8216), (2, 0, -2, -1, 4324),
    (2, 0, 1, 1, 4200), (2, 1, 0, -1, -3359), (2, -1, -1, 1, 2463), (2, -1, 0, 1, 2211),
    (2, -1, -1, -1, 2065),
)  # fmt: skip


def sun_ecliptic(jd: float) -> Ecliptic:
    """Apparent geocentric longitude/latitude."""
    t = centuries_since_j2000(jd)
    # Aberration (-0.00569°) and nutation in longitude turn the true longitude into the apparent one.
    lon = _sun_terms(t)[0] - 0.00569 - 0.00478 * sin_deg(_node_deg(t))
    return Ecliptic(norm_deg(lon), 0.0)


def sun_distance_km(jd: float) -> float:
    _, anomaly, ecc = _sun_terms(centuries_since_j2000(jd))
    au = 1.000001018 * (1 - ecc * ecc) / (1 + ecc * cos_deg(anomaly))
    return au * _AU_KM


def sun_equatorial(jd: float) -> Equatorial:
    return ecliptic_to_equatorial(sun_ecliptic(jd), _apparent_obliquity_deg(jd))


class MoonPosition(NamedTuple):
    ecl: Ecliptic  # apparent geocentric
    eq: Equatorial  # apparent geocentric
    distance_km: float  # Earth centre to Moon centre


def moon_position(jd: float) -> MoonPosition:
    t = centuries_since_j2000(jd)
    t2 = t * t
    t3 = t2 * t
    t4 = t3 * t
    lp = norm_deg(218.3164477 + 481267.88123421 * t - 0.0015786 * t2 + t3 / 538841 - t4 / 65194000)
    d = norm_deg(297.8501921 + 445267.1114034 * t - 0.0018819 * t2 + t3 / 545868 - t4 / 113065000)
    m = norm_deg(357.5291092 + 35999.0502909 * t - 0.0001536 * t2 + t3 / 24490000)
    mp = norm_deg(134.9633964 + 477198.8675055 * t + 0.0087414 * t2 + t3 / 69699 - t4 / 14712000)
    f = norm_deg(93.2720950 + 483202.0175233 * t - 0.0036539 * t2 - t3 / 3526000 + t4 / 863310000)
    a1 = 119.75 + 131.849 * t
    a2 = 53.09 + 479264.290 * t
    a3 = 313.45 + 481266.484 * t
    # Terms involving the Sun's anomaly M shrink as Earth's orbit becomes less eccentric.
    e = 1 - 0.002516 * t - 0.0000074 * t2
    e_factor = (1.0, e, e * e)

    sum_l = sum_r = sum_b = 0.0
    for kd, km, kmp, kf, kl, kr in _MOON_LON_DIST:
        arg = kd * d + km * m + kmp * mp + kf * f
        ef = e_factor[abs(km)]
        sum_l += kl * ef * sin_deg(arg)
        sum_r += kr * ef * cos_deg(arg)
    for kd, km, kmp, kf, kb in _MOON_LAT:
        sum_b += kb * e_factor[abs(km)] * sin_deg(kd * d + km * m + kmp * mp + kf * f)
    # Perturbations by Venus (A1), Jupiter (A2) and Earth's flattening (L' terms).
    sum_l += 3958 * sin_deg(a1) + 1962 * sin_deg(lp - f) + 318 * sin_deg(a2)
    sum_b += (
        -2235 * sin_deg(lp)
        + 382 * sin_deg(a3)
        + 175 * sin_deg(a1 - f)
        + 175 * sin_deg(a1 + f)
        + 127 * sin_deg(lp - mp)
        - 115 * sin_deg(lp + mp)
    )

    nutation_lon = -0.00478 * sin_deg(_node_deg(t))
    ecl = Ecliptic(norm_deg(lp + sum_l / 1e6 + nutation_lon), sum_b / 1e6)
    return MoonPosition(ecl, ecliptic_to_equatorial(ecl, _apparent_obliquity_deg(jd)), 385000.56 + sum_r / 1000)


def sun_horizontal(jd: float, lat_deg: float, lon_deg: float) -> Horizontal:
    return equatorial_to_horizontal(sun_equatorial(jd), lmst_deg(jd, lon_deg), lat_deg)


def moon_horizontal(jd: float, lat_deg: float, lon_deg: float) -> Horizontal:
    """The Moon's altitude is corrected for parallax, which can shift it by up
    to ~1° compared with the geocentric value."""
    moon = moon_position(jd)
    h = equatorial_to_horizontal(moon.eq, lmst_deg(jd, lon_deg), lat_deg)
    # Seen from the surface rather than Earth's centre, the Moon sits lower by
    # its horizontal parallax times cos(altitude).
    parallax = deg(math.asin(_EARTH_RADIUS_KM / moon.distance_km))
    return Horizontal(h.alt_deg - parallax * cos_deg(h.alt_deg), h.az_deg)


class MoonPhase(NamedTuple):
    illumination: float  # illuminated fraction of the disc, 0..1
    age_deg: float  # Moon minus Sun ecliptic longitude: 0 new, 180 full
    waxing: bool
    name: str  # "New Moon", "Waxing Crescent", ...


def moon_phase(jd: float) -> MoonPhase:
    moon = moon_position(jd)
    sun = sun_ecliptic(jd)
    sun_km = sun_distance_km(jd)

    # Geocentric elongation ψ, then the phase angle i seen from the Moon (Meeus 48.2, 48.3).
    cos_psi = cos_deg(moon.ecl.lat_deg) * cos_deg(moon.ecl.lon_deg - sun.lon_deg)
    psi = math.acos(cos_psi)
    i = math.atan2(sun_km * math.sin(psi), moon.distance_km - sun_km * cos_psi)
    illum = (1 + math.cos(i)) / 2

    age = norm_deg(moon.ecl.lon_deg - sun.lon_deg)
    # The four principal phases each get a ±7° (about half a day) window.
    if age < 7 or age >= 353:
        name = "New Moon"
    elif age < 83:
        name = "Waxing Crescent"
    elif age < 97:
        name = "First Quarter"
    elif age < 173:
        name = "Waxing Gibbous"
    elif age < 187:
        name = "Full Moon"
    elif age < 263:
        name = "Waning Gibbous"
    elif age < 277:
        name = "Last Quarter"
    else:
        name = "Waning Crescent"
    return MoonPhase(illum, age, age < 180, name)


class Crossing(NamedTuple):
    jd: float
    rising: bool  # true when the altitude goes up through the threshold


def find_crossings(
    altitude_deg: Callable[[float], float],
    jd0: float,
    jd1: float,
    threshold_deg: float,
    step_days: float = 10.0 / 1440,
) -> list[Crossing]:
    """Every time in [jd0, jd1] where altitude_deg(jd) crosses threshold_deg.

    The function is sampled every step_days and each crossing is refined by
    bisection to about a second, so step_days must be shorter than the gap
    between crossings."""
    out = []
    prev_t = jd0
    prev_v = altitude_deg(jd0) - threshold_deg
    while prev_t < jd1:
        t = min(prev_t + step_days, jd1)
        v = altitude_deg(t) - threshold_deg
        if (prev_v < 0) != (v < 0):
            lo, hi, lo_v = prev_t, t, prev_v
            while (hi - lo) * 86400 > 1:
                mid = (lo + hi) / 2
                mid_v = altitude_deg(mid) - threshold_deg
                if (mid_v < 0) == (lo_v < 0):
                    lo, lo_v = mid, mid_v
                else:
                    hi = mid
            out.append(Crossing((lo + hi) / 2, prev_v < 0))
        prev_t, prev_v = t, v
    return out


def first_crossing_after(xs: list[Crossing], jd: float, rising: bool) -> float | None:
    """First crossing after jd in the given direction."""
    for x in xs:
        if x.jd > jd and x.rising == rising:
            return x.jd
    return None


def last_crossing_before(xs: list[Crossing], jd: float, rising: bool) -> float | None:
    """Last crossing at or before jd in the given direction."""
    found = None
    for x in xs:
        if x.jd <= jd and x.rising == rising:
            found = x.jd
    return found


class Night(NamedTuple):
    """"Tonight" as seen at jd_now: the current night if the Sun is down,
    otherwise the next one. Near the poles the Sun may not set or rise at all;
    then polar is "day" or "night" and the window is simply the next 24 hours."""

    start: float  # sunset, or jd_now in the polar case
    end: float  # sunrise, or jd_now + 1 in the polar case
    polar: str | None  # None, "day" or "night"


def tonight(jd_now: float, lat_deg: float, lon_deg: float) -> Night:
    def sun_alt(jd: float) -> float:
        return sun_horizontal(jd, lat_deg, lon_deg).alt_deg

    xs = find_crossings(sun_alt, jd_now - 1, jd_now + 2, RISE_SET_ALT_DEG)
    if sun_alt(jd_now) < RISE_SET_ALT_DEG:
        sunset = last_crossing_before(xs, jd_now, False)
        sunrise = first_crossing_after(xs, jd_now, True)
        if sunset is None or sunrise is None:
            return Night(jd_now, jd_now + 1, "night")
    else:
        sunset = first_crossing_after(xs, jd_now, False)
        if sunset is None:
            return Night(jd_now, jd_now + 1, "day")
        sunrise = first_crossing_after(xs, sunset, True)
        if sunrise is None:
            return Night(jd_now, jd_now + 1, "night")
    return Night(sunset, sunrise, None)
