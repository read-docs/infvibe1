#include "astro/planets.hpp"

#include <algorithm>
#include <cmath>

#include "astro/time.hpp"

namespace astro {

namespace {

struct Elements {
    double a;     // semi-major axis, au
    double e;     // eccentricity
    double i;     // inclination, deg
    double L;     // mean longitude, deg
    double peri;  // longitude of perihelion, deg
    double node;  // longitude of the ascending node, deg
};

// Elements at J2000 and their rates per Julian century, referred to the J2000 ecliptic.
struct Orbit {
    Elements at2000;
    Elements rate;
};

constexpr Orbit kOrbits[] = {
    // Mercury
    {{0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593},
     {0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081}},
    // Venus
    {{0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255},
     {0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418}},
    // Mars
    {{1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891},
     {0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343}},
    // Jupiter
    {{5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909},
     {-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106}},
    // Saturn
    {{9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448},
     {-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794}},
    // Uranus
    {{19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503},
     {-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589}},
    // Neptune
    {{30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574},
     {0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664}},
};

// The Earth-Moon barycentre; it is within 5000 km of Earth's centre, which is
// negligible at planetary distances.
constexpr Orbit kEarth = {{1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0},
                          {0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0}};

constexpr double kLightAuPerDay = 173.1446327;
constexpr double kObliquityJ2000 = 23.43928;

// Solves Kepler's equation M = E - e sin E for the eccentric anomaly E (radians) by Newton's method.
double eccentricAnomaly(double meanAnomalyRad, double e) {
    double E = meanAnomalyRad + e * std::sin(meanAnomalyRad);
    for (int iter = 0; iter < 30; ++iter) {
        double dE = (meanAnomalyRad - (E - e * std::sin(E))) / (1 - e * std::cos(E));
        E += dE;
        if (std::abs(dE) < 1e-12) break;
    }
    return E;
}

// Heliocentric position in au, J2000 ecliptic frame.
Vec3 heliocentric(const Orbit& o, double jd) {
    double t = centuriesSinceJ2000(jd);
    const auto& p = o.at2000;
    const auto& r = o.rate;
    double a = p.a + r.a * t, e = p.e + r.e * t, inc = p.i + r.i * t;
    double L = p.L + r.L * t, peri = p.peri + r.peri * t, node = p.node + r.node * t;

    double argPeri = peri - node;
    double m = normDeg(L - peri);
    if (m > 180) m -= 360;
    double E = eccentricAnomaly(rad(m), e);

    // Position in the orbital plane, perihelion along +x.
    double xp = a * (std::cos(E) - e);
    double yp = a * std::sqrt(1 - e * e) * std::sin(E);

    double cw = cosDeg(argPeri), sw = sinDeg(argPeri);
    double cn = cosDeg(node), sn = sinDeg(node);
    double ci = cosDeg(inc), si = sinDeg(inc);
    return {(cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp,
            (cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp,
            (sw * si) * xp + (cw * si) * yp};
}

// Visual magnitude for phase angle i (degrees). Mercury and Venus use Mallama &
// Hilton (2018), whose fits hold up to the thin crescents near inferior
// conjunction; the rest use the Astronomical Almanac formulas in Meeus 41.
// ringTiltDeg is Earth's latitude above Saturn's ring plane; open rings make
// Saturn up to ~0.7 mag brighter.
double magnitude(Planet p, double r, double delta, double i, double ringTiltDeg) {
    double base = 5 * std::log10(r * delta);
    switch (p) {
        case Planet::Mercury:
            return base - 0.613 +
                   i * (6.3280e-02 + i * (-1.6336e-03 + i * (3.3644e-05 + i * (-3.4265e-07 + i * (1.6893e-09 + i * -3.0334e-12)))));
        case Planet::Venus:
            // Past 163.7° sunlight scattering forward through the atmosphere brightens the crescent again.
            if (i > 163.7) return base + 236.05828 - 2.81914 * i + 8.39034e-03 * i * i;
            return base - 4.384 + i * (-1.044e-03 + i * (3.687e-04 + i * (-2.814e-06 + i * 8.938e-09)));
        case Planet::Mars: return -1.52 + base + 0.016 * i;
        case Planet::Jupiter: return -9.40 + base + 0.005 * i;
        case Planet::Saturn: {
            double sb = std::abs(sinDeg(ringTiltDeg));
            return -8.88 + base - 2.60 * sb + 1.25 * sb * sb;
        }
        case Planet::Uranus: return -7.19 + base;
        case Planet::Neptune: return -6.87 + base;
    }
    return 0;
}

}  // namespace

const char* planetName(Planet p) {
    static const char* names[] = {"Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"};
    return names[int(p)];
}

PlanetPosition planetPosition(Planet p, double jd) {
    const Orbit& orbit = kOrbits[int(p)];
    Vec3 earth = heliocentric(kEarth, jd);

    // We see the planet where it was when the light left it: one light-time
    // iteration is enough (Jupiter moves ~0.005° during its ~40 min light time).
    Vec3 geo = heliocentric(orbit, jd) - earth;
    double tau = geo.norm() / kLightAuPerDay;
    Vec3 helio = heliocentric(orbit, jd - tau);
    geo = helio - earth;

    double delta = geo.norm(), r = helio.norm(), R = earth.norm();

    // J2000 ecliptic -> ecliptic of date: precession advances longitudes by ~1.397° per century.
    double t = centuriesSinceJ2000(jd);
    double lonJ2000 = deg(std::atan2(geo.y, geo.x));
    double lat = deg(std::asin(geo.z / delta));
    double nutation = -0.00478 * sinDeg(125.04 - 1934.136 * t);
    Ecliptic ecl{normDeg(lonJ2000 + 1.396971 * t + 0.0003086 * t * t + nutation), lat};
    Equatorial eq = eclipticToEquatorial(ecl, obliquityDeg(jd) + 0.00256 * cosDeg(125.04 - 1934.136 * t));

    double phase = deg(std::acos(std::clamp((r * r + delta * delta - R * R) / (2 * r * delta), -1.0, 1.0)));
    double elong = deg(std::acos(std::clamp((R * R + delta * delta - r * r) / (2 * R * delta), -1.0, 1.0)));

    double ringTilt = 0;
    if (p == Planet::Saturn) {
        // Angle between the line of sight and the ring plane, from the ring pole
        // (RA 40.589°, Dec 83.537°, J2000) and Saturn's J2000 equatorial direction.
        Equatorial sat = eclipticToEquatorial({lonJ2000, lat}, kObliquityJ2000);
        double poleRa = 40.589, poleDec = 83.537;
        ringTilt = deg(std::asin(sinDeg(poleDec) * sinDeg(sat.decDeg) +
                                 cosDeg(poleDec) * cosDeg(sat.decDeg) * cosDeg(poleRa - sat.raDeg)));
    }

    return {eq, delta, r, elong, phase, magnitude(p, r, delta, phase, ringTilt)};
}

Horizontal planetHorizontal(Planet p, double jd, double latDeg, double lonDeg) {
    return equatorialToHorizontal(planetPosition(p, jd).eq, lmstDeg(jd, lonDeg), latDeg);
}

}  // namespace astro
