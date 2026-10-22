#pragma once

#include <cmath>

namespace astro {

constexpr double kPi = 3.14159265358979323846;
constexpr double kDeg = kPi / 180.0;  // multiply degrees by this to get radians

inline double rad(double deg) { return deg * kDeg; }
inline double deg(double rad) { return rad / kDeg; }
inline double sinDeg(double d) { return std::sin(d * kDeg); }
inline double cosDeg(double d) { return std::cos(d * kDeg); }

// Wraps an angle into [0, 360).
inline double normDeg(double d) {
    d = std::fmod(d, 360.0);
    return d < 0 ? d + 360.0 : d;
}

struct Vec3 {
    double x, y, z;
    Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
    Vec3 operator*(double k) const { return {x * k, y * k, z * k}; }
    double dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
    double norm() const { return std::sqrt(dot(*this)); }
};

struct Ecliptic {
    double lonDeg;
    double latDeg;
};

struct Equatorial {
    double raDeg;
    double decDeg;
};

// altDeg is above the horizon; azDeg is measured from north through east.
struct Horizontal {
    double altDeg;
    double azDeg;
};

// Mean obliquity of the ecliptic in degrees (Meeus eq. 22.2, truncated).
double obliquityDeg(double jd);

Equatorial eclipticToEquatorial(const Ecliptic& ecl, double obliquityDeg);

// lstDeg is local sidereal time; latDeg is the observer's latitude.
Horizontal equatorialToHorizontal(const Equatorial& eq, double lstDeg, double latDeg);

// --- Earth-fixed coordinates, for satellites. Distances in km.

// A point on or above the WGS-84 ellipsoid.
struct Geodetic {
    double latDeg;
    double lonDeg;  // east-positive, [-180, 180)
    double altKm;   // above the ellipsoid
};

// TEME (the SGP4 output frame) to Earth-fixed, by rotating through Greenwich
// sidereal time. Polar motion (~10 m) is ignored.
Vec3 temeToEcef(const Vec3& teme, double jd);
Vec3 geodeticToEcef(const Geodetic& g);
Geodetic ecefToGeodetic(const Vec3& ecef);

// Where an Earth-fixed point appears from an observer: altitude/azimuth and distance.
struct LookAngles {
    Horizontal h;
    double rangeKm;
};
LookAngles lookAngles(const Vec3& targetEcef, const Geodetic& observer);

// Unit vector from Earth towards the Sun in the TEME frame (close enough to the
// apparent equator and equinox of date that sunEquatorial gives).
Vec3 sunDirectionTeme(double jd);

// True if a point (TEME, km) is inside Earth's cylindrical shadow. Ignoring the
// penumbra shifts shadow entry by a few seconds at most.
bool inEarthShadow(const Vec3& teme, const Vec3& sunDir);

// "N", "NNE", ... for an azimuth in degrees.
const char* compassPoint(double azDeg);

}  // namespace astro
