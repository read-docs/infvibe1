"""Satellite visibility and pass prediction."""

import math
from dataclasses import dataclass
from typing import NamedTuple

from skywatch.astro.coords import (
    Geodetic,
    LookAngles,
    ecef_to_geodetic,
    geodetic_to_ecef,
    in_earth_shadow,
    look_angles,
    norm,
    sun_direction_teme,
    teme_to_ecef,
)
from skywatch.astro.sgp4 import Sgp4
from skywatch.astro.sun_moon import find_crossings, sun_horizontal

# Typical standard magnitudes (at 1000 km range, half lit), as Heavens-Above uses.
ISS_STD_MAGNITUDE = -1.8
STARLINK_STD_MAGNITUDE = 5.0

_SECOND = 1.0 / 86400
_DARK_SUN_ALT_DEG = -6
_MIN_VISIBLE_ALT_DEG = 10


def _altitude_of(sat: Sgp4, jd: float, obs: Geodetic) -> float:
    return look_angles(teme_to_ecef(sat.at(jd).r, jd), obs).h.alt_deg


def _phase_factor(phase_rad: float) -> float:
    """Brightness of a diffusely reflecting sphere: the phase angle
    (Sun-satellite-observer) decides how much of the lit side faces us.
    Normalised to 1 at 90°."""
    return math.sin(phase_rad) + (math.pi - phase_rad) * math.cos(phase_rad)


class SatelliteView(NamedTuple):
    """A satellite as seen by an observer at one moment."""

    subpoint: Geodetic  # the point on Earth directly below, with the satellite's altitude
    look: LookAngles
    speed_km_s: float  # inertial
    sunlit: bool
    magnitude: float  # estimated brightness if sunlit


def view_satellite(sat: Sgp4, jd: float, observer: Geodetic, std_magnitude: float) -> SatelliteView:
    state = sat.at(jd)
    ecef = teme_to_ecef(state.r, jd)
    sun_teme = sun_direction_teme(jd)
    look = look_angles(ecef, observer)

    sunlit = not in_earth_shadow(state.r, sun_teme)
    o = geodetic_to_ecef(observer)
    to_observer = (o[0] - ecef[0], o[1] - ecef[1], o[2] - ecef[2])
    sun_ecef = teme_to_ecef(sun_teme, jd)
    cos_phase = (sun_ecef[0] * to_observer[0] + sun_ecef[1] * to_observer[1] + sun_ecef[2] * to_observer[2]) / norm(
        to_observer
    )
    phase = math.acos(max(-1.0, min(1.0, cos_phase)))
    factor = max(_phase_factor(phase), 1e-6)
    mag = std_magnitude + 5 * math.log10(look.range_km / 1000) - 2.5 * math.log10(factor)

    return SatelliteView(ecef_to_geodetic(ecef), look, norm(state.v), sunlit, mag)


def subpoint(sat: Sgp4, jd: float) -> Geodetic:
    """Where a satellite is over the Earth, without an observer."""
    return ecef_to_geodetic(teme_to_ecef(sat.at(jd).r, jd))


class PassPoint(NamedTuple):
    jd: float
    alt_deg: float
    az_deg: float


@dataclass
class Pass:
    """One pass above the observer's horizon.

    The visible part is where the satellite is sunlit while the observer's sky
    is dark (Sun below -6°): only then can it be seen."""

    rise: PassPoint
    peak: PassPoint
    set: PassPoint
    visible: bool = False  # a visible part exists and reaches at least 10° up
    visible_start: PassPoint | None = None
    visible_end: PassPoint | None = None
    visible_max_alt_deg: float = 0.0
    brightest_magnitude: float = 99.0


def find_passes(sat: Sgp4, obs: Geodetic, jd0: float, jd1: float, std_magnitude: float) -> list[Pass]:
    """Passes that are still above the horizon at jd0 or rise before jd1,
    searched in 30-second steps (passes shorter than that are skipped)."""

    def alt(jd: float) -> float:
        return _altitude_of(sat, jd, obs)

    def point(jd: float) -> PassPoint:
        h = look_angles(teme_to_ecef(sat.at(jd).r, jd), obs).h
        return PassPoint(jd, h.alt_deg, h.az_deg)

    # Start a little early so a pass already in progress at jd0 has its rise.
    xs = find_crossings(alt, jd0 - 20.0 / 1440, jd1, 0, 30 * _SECOND)

    passes = []
    for x, nxt in zip(xs, xs[1:]):
        if not x.rising or nxt.rising:
            continue
        rise, set_ = x.jd, nxt.jd
        if set_ < jd0:
            continue

        # The altitude has a single maximum during a pass: golden-section search.
        a, b = rise, set_
        g = (math.sqrt(5.0) - 1) / 2
        while (b - a) > _SECOND:
            c, d = b - g * (b - a), a + g * (b - a)
            if alt(c) > alt(d):
                b = d
            else:
                a = c
        peak = (a + b) / 2

        p = Pass(point(rise), point(peak), point(set_))

        # Walk the pass in 10-second steps to find the visible part.
        jd = rise
        while jd <= set_:
            if sun_horizontal(jd, obs.lat_deg, obs.lon_deg).alt_deg <= _DARK_SUN_ALT_DEG:
                v = view_satellite(sat, jd, obs, std_magnitude)
                if v.sunlit and v.look.h.alt_deg > 0:
                    pt = PassPoint(jd, v.look.h.alt_deg, v.look.h.az_deg)
                    if p.visible_start is None:
                        p.visible_start = pt
                    p.visible_end = pt
                    p.visible_max_alt_deg = max(p.visible_max_alt_deg, pt.alt_deg)
                    p.brightest_magnitude = min(p.brightest_magnitude, v.magnitude)
            jd += 10 * _SECOND
        p.visible = p.visible_start is not None and p.visible_max_alt_deg >= _MIN_VISIBLE_ALT_DEG
        passes.append(p)
    return passes
