"""Planet positions from JPL's approximate Keplerian elements (E. M. Standish,
"Keplerian Elements for Approximate Positions of the Major Planets", table 1,
valid 1800-2050) and visual magnitudes from Meeus chapter 41. Accurate to a few
arcminutes, which is far below what matters for "where do I look"."""

import math
from typing import NamedTuple

from skywatch.astro.coords import (
    Ecliptic,
    Equatorial,
    Horizontal,
    Vec3,
    cos_deg,
    deg,
    ecliptic_to_equatorial,
    equatorial_to_horizontal,
    norm,
    norm_deg,
    obliquity_deg,
    rad,
    sin_deg,
    sub,
)
from skywatch.astro.time import centuries_since_j2000, lmst_deg

PLANETS = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune")

# A planet is a point, so at rise/set only refraction (34') lifts it.
PLANET_RISE_SET_ALT_DEG = -0.5667

# Elements at J2000 and their rates per Julian century, referred to the J2000
# ecliptic: a (au), e, i (deg), L mean longitude, longitude of perihelion,
# longitude of the ascending node (deg).
_ORBITS = {
    "Mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081)),
    "Venus": ((0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
              (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418)),
    "Mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
    "Jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106)),
    "Saturn": ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
               (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794)),
    "Uranus": ((19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503),
               (-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589)),
    "Neptune": ((30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574),
                (0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664)),
}  # fmt: skip

# The Earth-Moon barycentre; it is within 5000 km of Earth's centre, which is
# negligible at planetary distances.
_EARTH = ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
          (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0))  # fmt: skip

_LIGHT_AU_PER_DAY = 173.1446327
_OBLIQUITY_J2000 = 23.43928


def _eccentric_anomaly(mean_anomaly_rad: float, e: float) -> float:
    """Solves Kepler's equation M = E - e sin E for the eccentric anomaly E
    (radians) by Newton's method."""
    E = mean_anomaly_rad + e * math.sin(mean_anomaly_rad)
    for _ in range(30):
        dE = (mean_anomaly_rad - (E - e * math.sin(E))) / (1 - e * math.cos(E))
        E += dE
        if abs(dE) < 1e-12:
            break
    return E


def _heliocentric(orbit, jd: float) -> Vec3:
    """Heliocentric position in au, J2000 ecliptic frame."""
    t = centuries_since_j2000(jd)
    a, e, inc, L, peri, node = (p + r * t for p, r in zip(*orbit))

    arg_peri = peri - node
    m = norm_deg(L - peri)
    if m > 180:
        m -= 360
    E = _eccentric_anomaly(rad(m), e)

    # Position in the orbital plane, perihelion along +x.
    xp = a * (math.cos(E) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(E)

    cw, sw = cos_deg(arg_peri), sin_deg(arg_peri)
    cn, sn = cos_deg(node), sin_deg(node)
    ci, si = cos_deg(inc), sin_deg(inc)
    return (
        (cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp,
        (cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp,
        (sw * si) * xp + (cw * si) * yp,
    )


def _magnitude(planet: str, r: float, delta: float, i: float, ring_tilt_deg: float) -> float:
    """Visual magnitude for phase angle i (degrees).

    Mercury and Venus use Mallama & Hilton (2018), whose fits hold up to the
    thin crescents near inferior conjunction; the rest use the Astronomical
    Almanac formulas in Meeus 41. ring_tilt_deg is Earth's latitude above
    Saturn's ring plane; open rings make Saturn up to ~0.7 mag brighter."""
    base = 5 * math.log10(r * delta)
    if planet == "Mercury":
        return (
            base
            - 0.613
            + i * (6.3280e-02 + i * (-1.6336e-03 + i * (3.3644e-05 + i * (-3.4265e-07 + i * (1.6893e-09 + i * -3.0334e-12)))))
        )
    if planet == "Venus":
        # Past 163.7° sunlight scattering forward through the atmosphere brightens the crescent again.
        if i > 163.7:
            return base + 236.05828 - 2.81914 * i + 8.39034e-03 * i * i
        return base - 4.384 + i * (-1.044e-03 + i * (3.687e-04 + i * (-2.814e-06 + i * 8.938e-09)))
    if planet == "Mars":
        return -1.52 + base + 0.016 * i
    if planet == "Jupiter":
        return -9.40 + base + 0.005 * i
    if planet == "Saturn":
        sb = abs(sin_deg(ring_tilt_deg))
        return -8.88 + base - 2.60 * sb + 1.25 * sb * sb
    if planet == "Uranus":
        return -7.19 + base
    return -6.87 + base  # Neptune


class PlanetPosition(NamedTuple):
    eq: Equatorial  # apparent geocentric, equinox of date
    distance_au: float  # from Earth
    sun_distance_au: float  # from the Sun
    elongation_deg: float  # angle between the planet and the Sun, seen from Earth
    phase_angle_deg: float  # angle Sun-planet-Earth; 0 means fully lit
    magnitude: float


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def planet_position(planet: str, jd: float) -> PlanetPosition:
    orbit = _ORBITS[planet]
    earth = _heliocentric(_EARTH, jd)

    # We see the planet where it was when the light left it: one light-time
    # iteration is enough (Jupiter moves ~0.005° during its ~40 min light time).
    geo = sub(_heliocentric(orbit, jd), earth)
    tau = norm(geo) / _LIGHT_AU_PER_DAY
    helio = _heliocentric(orbit, jd - tau)
    geo = sub(helio, earth)

    delta, r, R = norm(geo), norm(helio), norm(earth)

    # J2000 ecliptic -> ecliptic of date: precession advances longitudes by ~1.397° per century.
    t = centuries_since_j2000(jd)
    lon_j2000 = deg(math.atan2(geo[1], geo[0]))
    lat = deg(math.asin(geo[2] / delta))
    nutation = -0.00478 * sin_deg(125.04 - 1934.136 * t)
    ecl = Ecliptic(norm_deg(lon_j2000 + 1.396971 * t + 0.0003086 * t * t + nutation), lat)
    eq = ecliptic_to_equatorial(ecl, obliquity_deg(jd) + 0.00256 * cos_deg(125.04 - 1934.136 * t))

    phase = deg(math.acos(_clamp((r * r + delta * delta - R * R) / (2 * r * delta), -1.0, 1.0)))
    elong = deg(math.acos(_clamp((R * R + delta * delta - r * r) / (2 * R * delta), -1.0, 1.0)))

    ring_tilt = 0.0
    if planet == "Saturn":
        # Angle between the line of sight and the ring plane, from the ring pole
        # (RA 40.589°, Dec 83.537°, J2000) and Saturn's J2000 equatorial direction.
        sat = ecliptic_to_equatorial(Ecliptic(lon_j2000, lat), _OBLIQUITY_J2000)
        pole_ra, pole_dec = 40.589, 83.537
        ring_tilt = deg(
            math.asin(
                sin_deg(pole_dec) * sin_deg(sat.dec_deg)
                + cos_deg(pole_dec) * cos_deg(sat.dec_deg) * cos_deg(pole_ra - sat.ra_deg)
            )
        )

    return PlanetPosition(eq, delta, r, elong, phase, _magnitude(planet, r, delta, phase, ring_tilt))


def planet_horizontal(planet: str, jd: float, lat_deg: float, lon_deg: float) -> Horizontal:
    return equatorial_to_horizontal(planet_position(planet, jd).eq, lmst_deg(jd, lon_deg), lat_deg)
