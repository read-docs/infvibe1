#include "astro/time.hpp"

#include "astro/coords.hpp"

namespace astro {

double jdFromUnix(double unixSeconds) { return unixSeconds / 86400.0 + 2440587.5; }

double unixFromJd(double jd) { return (jd - 2440587.5) * 86400.0; }

double centuriesSinceJ2000(double jd) { return (jd - kJ2000) / 36525.0; }

double gmstDeg(double jd) {
    double t = centuriesSinceJ2000(jd);
    return normDeg(280.46061837 + 360.98564736629 * (jd - kJ2000) + 0.000387933 * t * t -
                   t * t * t / 38710000.0);
}

double lmstDeg(double jd, double lonDeg) { return normDeg(gmstDeg(jd) + lonDeg); }

}  // namespace astro
