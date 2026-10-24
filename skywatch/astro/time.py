"""Time scales used by the astronomy code.

Times are passed around as Julian Dates (days); the server converts from Unix
seconds at the edges. UT and TT differ by ~69 s, which is below what the
low-precision formulas here can resolve, so they are treated as equal.
"""

import math

J2000 = 2451545.0  # 2000-01-01 12:00 UT


def jd_from_unix(unix_seconds: float) -> float:
    return unix_seconds / 86400.0 + 2440587.5


def unix_from_jd(jd: float) -> float:
    return (jd - 2440587.5) * 86400.0


def centuries_since_j2000(jd: float) -> float:
    """Julian centuries since J2000."""
    return (jd - J2000) / 36525.0


def _norm_deg(d: float) -> float:
    d = math.fmod(d, 360.0)
    return d + 360.0 if d < 0 else d


def gmst_deg(jd: float) -> float:
    """Greenwich mean sidereal time in degrees [0, 360) (Meeus eq. 12.4)."""
    t = centuries_since_j2000(jd)
    return _norm_deg(280.46061837 + 360.98564736629 * (jd - J2000) + 0.000387933 * t * t - t * t * t / 38710000.0)


def lmst_deg(jd: float, lon_deg: float) -> float:
    """Local mean sidereal time in degrees [0, 360); lon_deg is east-positive."""
    return _norm_deg(gmst_deg(jd) + lon_deg)
