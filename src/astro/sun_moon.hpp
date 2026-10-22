#pragma once

#include <functional>
#include <optional>
#include <vector>

#include "astro/coords.hpp"

// Low-precision Sun and Moon positions after Meeus, "Astronomical Algorithms"
// (2nd ed.), chapters 25, 47 and 48. Accurate to about 0.01° (Sun) and a few
// arcminutes (Moon), which keeps rise/set times within a minute or two.
namespace astro {

// Altitude of the Sun's centre at sunrise/sunset: refraction (34') plus the
// Sun's radius (16'). The Moon's radius is about the same, so moonrise uses it too.
constexpr double kRiseSetAltDeg = -0.833;

Ecliptic sunEcliptic(double jd);  // apparent geocentric longitude/latitude
double sunDistanceKm(double jd);
Equatorial sunEquatorial(double jd);

struct MoonPosition {
    Ecliptic ecl;       // apparent geocentric
    Equatorial eq;      // apparent geocentric
    double distanceKm;  // Earth centre to Moon centre
};
MoonPosition moonPosition(double jd);

// Positions in the observer's sky. The Moon's altitude is corrected for
// parallax, which can shift it by up to ~1° compared with the geocentric value.
Horizontal sunHorizontal(double jd, double latDeg, double lonDeg);
Horizontal moonHorizontal(double jd, double latDeg, double lonDeg);

struct MoonPhase {
    double illumination;  // illuminated fraction of the disc, 0..1
    double ageDeg;        // Moon minus Sun ecliptic longitude: 0 new, 180 full
    bool waxing;
    const char* name;     // "New Moon", "Waxing Crescent", ...
};
MoonPhase moonPhase(double jd);

struct Crossing {
    double jd;
    bool rising;  // true when the altitude goes up through the threshold
};

// Every time in [jd0, jd1] where altitudeDeg(jd) crosses thresholdDeg. The
// function is sampled every stepDays and each crossing is refined by bisection
// to about a second, so stepDays must be shorter than the gap between crossings.
std::vector<Crossing> findCrossings(const std::function<double(double)>& altitudeDeg, double jd0,
                                    double jd1, double thresholdDeg, double stepDays = 10.0 / 1440);

// First crossing after jd in the given direction.
std::optional<double> firstCrossingAfter(const std::vector<Crossing>& xs, double jd, bool rising);
// Last crossing at or before jd in the given direction.
std::optional<double> lastCrossingBefore(const std::vector<Crossing>& xs, double jd, bool rising);

// "Tonight" as seen at jdNow: the current night if the Sun is down, otherwise
// the next one. Near the poles the Sun may not set or rise at all; then
// polar is "day" or "night" and the window is simply the next 24 hours.
struct Night {
    double start;  // sunset, or jdNow in the polar case
    double end;    // sunrise, or jdNow + 1 in the polar case
    const char* polar;  // nullptr, "day" or "night"
};
Night tonight(double jdNow, double latDeg, double lonDeg);

}  // namespace astro
