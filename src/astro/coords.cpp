#include "astro/coords.hpp"

#include "astro/sun_moon.hpp"
#include "astro/time.hpp"

namespace astro {

double obliquityDeg(double jd) {
    double t = centuriesSinceJ2000(jd);
    return 23.4392911 - 0.0130042 * t;
}

Equatorial eclipticToEquatorial(const Ecliptic& ecl, double eps) {
    double sl = sinDeg(ecl.lonDeg), cl = cosDeg(ecl.lonDeg);
    double sb = sinDeg(ecl.latDeg), cb = cosDeg(ecl.latDeg);
    double se = sinDeg(eps), ce = cosDeg(eps);
    double ra = std::atan2(sl * ce - (sb / cb) * se, cl);
    double dec = std::asin(sb * ce + cb * se * sl);
    return {normDeg(deg(ra)), deg(dec)};
}

Horizontal equatorialToHorizontal(const Equatorial& eq, double lstDeg, double latDeg) {
    double h = lstDeg - eq.raDeg;  // hour angle
    double sd = sinDeg(eq.decDeg), cd = cosDeg(eq.decDeg);
    double sp = sinDeg(latDeg), cp = cosDeg(latDeg);
    double alt = std::asin(sp * sd + cp * cd * cosDeg(h));
    double az = std::atan2(-cd * sinDeg(h), sd * cp - cd * sp * cosDeg(h));
    return {deg(alt), normDeg(deg(az))};
}

namespace {
constexpr double kWgs84A = 6378.137;               // equatorial radius, km
constexpr double kWgs84F = 1 / 298.257223563;      // flattening
constexpr double kWgs84E2 = kWgs84F * (2 - kWgs84F);  // first eccentricity squared
}  // namespace

Vec3 temeToEcef(const Vec3& r, double jd) {
    double g = rad(gmstDeg(jd));
    double c = std::cos(g), s = std::sin(g);
    return {c * r.x + s * r.y, -s * r.x + c * r.y, r.z};
}

Vec3 geodeticToEcef(const Geodetic& g) {
    double sl = sinDeg(g.latDeg), cl = cosDeg(g.latDeg);
    double n = kWgs84A / std::sqrt(1 - kWgs84E2 * sl * sl);  // prime vertical radius
    return {(n + g.altKm) * cl * cosDeg(g.lonDeg), (n + g.altKm) * cl * sinDeg(g.lonDeg),
            (n * (1 - kWgs84E2) + g.altKm) * sl};
}

Geodetic ecefToGeodetic(const Vec3& r) {
    double p = std::hypot(r.x, r.y);
    double lon = deg(std::atan2(r.y, r.x));
    // Iterate on latitude; converges to well under a millimetre in a few rounds.
    double lat = std::atan2(r.z, p * (1 - kWgs84E2));
    double n = kWgs84A, alt = 0;
    for (int i = 0; i < 6; ++i) {
        double sl = std::sin(lat);
        n = kWgs84A / std::sqrt(1 - kWgs84E2 * sl * sl);
        alt = p / std::cos(lat) - n;
        lat = std::atan2(r.z, p * (1 - kWgs84E2 * n / (n + alt)));
    }
    return {deg(lat), lon, alt};
}

LookAngles lookAngles(const Vec3& target, const Geodetic& obs) {
    Vec3 d = target - geodeticToEcef(obs);
    double sl = sinDeg(obs.latDeg), cl = cosDeg(obs.latDeg);
    double so = sinDeg(obs.lonDeg), co = cosDeg(obs.lonDeg);
    // Rotate into the observer's south-east-zenith frame.
    double south = sl * co * d.x + sl * so * d.y - cl * d.z;
    double east = -so * d.x + co * d.y;
    double up = cl * co * d.x + cl * so * d.y + sl * d.z;
    double range = d.norm();
    return {{deg(std::asin(up / range)), normDeg(deg(std::atan2(east, -south)))}, range};
}

Vec3 sunDirectionTeme(double jd) {
    auto eq = sunEquatorial(jd);
    double cd = cosDeg(eq.decDeg);
    return {cd * cosDeg(eq.raDeg), cd * sinDeg(eq.raDeg), sinDeg(eq.decDeg)};
}

bool inEarthShadow(const Vec3& r, const Vec3& sunDir) {
    double along = r.dot(sunDir);
    if (along > 0) return false;  // on the day side
    Vec3 perp = r - sunDir * along;
    return perp.norm() < kWgs84A;
}

const char* compassPoint(double azDeg) {
    static const char* names[] = {"N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"};
    return names[int(normDeg(azDeg + 11.25) / 22.5) % 16];
}

}  // namespace astro
