#pragma once

// Time scales used by the astronomy code. Times are passed around as Julian
// Dates (days); the server converts from Unix seconds at the edges.
// UT and TT differ by ~69 s, which is below what the low-precision formulas
// here can resolve, so they are treated as equal.
namespace astro {

constexpr double kJ2000 = 2451545.0;  // 2000-01-01 12:00 UT

double jdFromUnix(double unixSeconds);
double unixFromJd(double jd);

// Julian centuries since J2000.
double centuriesSinceJ2000(double jd);

// Greenwich mean sidereal time in degrees [0, 360) (Meeus eq. 12.4).
double gmstDeg(double jd);

// Local mean sidereal time in degrees [0, 360); lonDeg is east-positive.
double lmstDeg(double jd, double lonDeg);

}  // namespace astro
