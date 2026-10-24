"""Coordinate systems and conversions.

Vectors are plain (x, y, z) tuples, which keeps the satellite loops fast.
Distances are in km.
"""

import math
from typing import NamedTuple

from skywatch.astro.time import centuries_since_j2000, gmst_deg

DEG = math.pi / 180.0  # multiply degrees by this to get radians

Vec3 = tuple[float, float, float]


def rad(deg_: float) -> float:
    return deg_ * DEG


def deg(rad_: float) -> float:
    return rad_ / DEG


def sin_deg(d: float) -> float:
    return math.sin(d * DEG)


def cos_deg(d: float) -> float:
    return math.cos(d * DEG)


def norm_deg(d: float) -> float:
    """Wraps an angle into [0, 360)."""
    d = math.fmod(d, 360.0)
    return d + 360.0 if d < 0 else d


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


class Ecliptic(NamedTuple):
    lon_deg: float
    lat_deg: float


class Equatorial(NamedTuple):
    ra_deg: float
    dec_deg: float


class Horizontal(NamedTuple):
    """alt_deg is above the horizon; az_deg is measured from north through east."""

    alt_deg: float
    az_deg: float


def obliquity_deg(jd: float) -> float:
    """Mean obliquity of the ecliptic in degrees (Meeus eq. 22.2, truncated)."""
    t = centuries_since_j2000(jd)
    return 23.4392911 - 0.0130042 * t


def ecliptic_to_equatorial(ecl: Ecliptic, eps: float) -> Equatorial:
    sl, cl = sin_deg(ecl.lon_deg), cos_deg(ecl.lon_deg)
    sb, cb = sin_deg(ecl.lat_deg), cos_deg(ecl.lat_deg)
    se, ce = sin_deg(eps), cos_deg(eps)
    ra = math.atan2(sl * ce - (sb / cb) * se, cl)
    dec = math.asin(sb * ce + cb * se * sl)
    return Equatorial(norm_deg(deg(ra)), deg(dec))


def equatorial_to_horizontal(eq: Equatorial, lst_deg: float, lat_deg: float) -> Horizontal:
    """lst_deg is local sidereal time; lat_deg is the observer's latitude."""
    h = lst_deg - eq.ra_deg  # hour angle
    sd, cd = sin_deg(eq.dec_deg), cos_deg(eq.dec_deg)
    sp, cp = sin_deg(lat_deg), cos_deg(lat_deg)
    alt = math.asin(sp * sd + cp * cd * cos_deg(h))
    az = math.atan2(-cd * sin_deg(h), sd * cp - cd * sp * cos_deg(h))
    return Horizontal(deg(alt), norm_deg(deg(az)))


# --- Earth-fixed coordinates, for satellites.

WGS84_A = 6378.137  # equatorial radius, km
WGS84_F = 1 / 298.257223563  # flattening
WGS84_E2 = WGS84_F * (2 - WGS84_F)  # first eccentricity squared


class Geodetic(NamedTuple):
    """A point on or above the WGS-84 ellipsoid."""

    lat_deg: float
    lon_deg: float  # east-positive, [-180, 180)
    alt_km: float  # above the ellipsoid


def teme_to_ecef(r: Vec3, jd: float) -> Vec3:
    """TEME (the SGP4 output frame) to Earth-fixed, by rotating through
    Greenwich sidereal time. Polar motion (~10 m) is ignored."""
    g = rad(gmst_deg(jd))
    c, s = math.cos(g), math.sin(g)
    return (c * r[0] + s * r[1], -s * r[0] + c * r[1], r[2])


def geodetic_to_ecef(g: Geodetic) -> Vec3:
    sl, cl = sin_deg(g.lat_deg), cos_deg(g.lat_deg)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sl * sl)  # prime vertical radius
    return (
        (n + g.alt_km) * cl * cos_deg(g.lon_deg),
        (n + g.alt_km) * cl * sin_deg(g.lon_deg),
        (n * (1 - WGS84_E2) + g.alt_km) * sl,
    )


def ecef_to_geodetic(r: Vec3) -> Geodetic:
    x, y, z = r
    p = math.hypot(x, y)
    lon = deg(math.atan2(y, x))
    # Iterate on latitude; converges to well under a millimetre in a few rounds.
    lat = math.atan2(z, p * (1 - WGS84_E2))
    n, alt = WGS84_A, 0.0
    for _ in range(6):
        sl = math.sin(lat)
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * sl * sl)
        alt = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - WGS84_E2 * n / (n + alt)))
    return Geodetic(deg(lat), lon, alt)


class LookAngles(NamedTuple):
    """Where an Earth-fixed point appears from an observer: altitude/azimuth and distance."""

    h: Horizontal
    range_km: float


def look_angles(target: Vec3, obs: Geodetic) -> LookAngles:
    o = geodetic_to_ecef(obs)
    dx, dy, dz = target[0] - o[0], target[1] - o[1], target[2] - o[2]
    sl, cl = sin_deg(obs.lat_deg), cos_deg(obs.lat_deg)
    so, co = sin_deg(obs.lon_deg), cos_deg(obs.lon_deg)
    # Rotate into the observer's south-east-zenith frame.
    south = sl * co * dx + sl * so * dy - cl * dz
    east = -so * dx + co * dy
    up = cl * co * dx + cl * so * dy + sl * dz
    rng = math.sqrt(dx * dx + dy * dy + dz * dz)
    return LookAngles(Horizontal(deg(math.asin(up / rng)), norm_deg(deg(math.atan2(east, -south)))), rng)


def sun_direction_teme(jd: float) -> Vec3:
    """Unit vector from Earth towards the Sun in the TEME frame (close enough to
    the apparent equator and equinox of date that sun_equatorial gives)."""
    from skywatch.astro.sun_moon import sun_equatorial  # sun_moon imports this module

    eq = sun_equatorial(jd)
    cd = cos_deg(eq.dec_deg)
    return (cd * cos_deg(eq.ra_deg), cd * sin_deg(eq.ra_deg), sin_deg(eq.dec_deg))


def in_earth_shadow(r: Vec3, sun_dir: Vec3) -> bool:
    """True if a point (TEME, km) is inside Earth's cylindrical shadow. Ignoring
    the penumbra shifts shadow entry by a few seconds at most."""
    along = dot(r, sun_dir)
    if along > 0:
        return False  # on the day side
    perp = (r[0] - sun_dir[0] * along, r[1] - sun_dir[1] * along, r[2] - sun_dir[2] * along)
    return norm(perp) < WGS84_A


_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass_point(az_deg: float) -> str:
    """"N", "NNE", ... for an azimuth in degrees."""
    return _COMPASS[int(norm_deg(az_deg + 11.25) / 22.5) % 16]
