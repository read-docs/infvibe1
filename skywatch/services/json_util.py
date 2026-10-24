"""Small helpers for turning astronomy results into the JSON the frontend reads."""

import math

from skywatch.astro.coords import Horizontal, compass_point
from skywatch.astro.time import unix_from_jd


def round_half_away(x: float) -> float:
    """Rounds halves away from zero, like C's round(). Python's round() rounds
    halves to even, which would make 87.5 a score of 88 but 86.5 one of 86."""
    if not math.isfinite(x):
        return x
    a = abs(x)
    r = math.floor(a)
    if a - r >= 0.5:  # exact for doubles, unlike floor(a + 0.5)
        r += 1
    return math.copysign(r, x)


def iround(x: float) -> int:
    """Nearest integer, halves away from zero."""
    return int(round_half_away(x))


def round1(x: float) -> float:
    return round_half_away(x * 10) / 10


def round2(x: float) -> float:
    return round_half_away(x * 100) / 100


def round3(x: float) -> float:
    return round_half_away(x * 1000) / 1000


def unix_or_none(jd: float | None) -> int | None:
    """A Julian Date as whole Unix seconds, or None."""
    return None if jd is None else iround(unix_from_jd(jd))


def sky_position(h: Horizontal) -> dict:
    """{alt, az, direction} rounded to 0.1°."""
    return {"alt": round1(h.alt_deg), "az": round1(h.az_deg), "direction": compass_point(h.az_deg)}
