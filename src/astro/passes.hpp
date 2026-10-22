#pragma once

#include <optional>
#include <vector>

#include "astro/coords.hpp"
#include "astro/sgp4.hpp"

namespace astro {

// Typical standard magnitudes (at 1000 km range, half lit), as Heavens-Above uses.
constexpr double kIssStdMagnitude = -1.8;
constexpr double kStarlinkStdMagnitude = 5.0;

// A satellite as seen by an observer at one moment.
struct SatelliteView {
    Geodetic subpoint;  // the point on Earth directly below, with the satellite's altitude
    LookAngles look;
    double speedKmS;    // inertial
    bool sunlit;
    double magnitude;   // estimated brightness if sunlit
};
SatelliteView viewSatellite(const Sgp4& sat, double jd, const Geodetic& observer, double stdMagnitude);

// Where a satellite is over the Earth, without an observer.
Geodetic subpoint(const Sgp4& sat, double jd);

struct PassPoint {
    double jd;
    double altDeg;
    double azDeg;
};

// One pass above the observer's horizon.
struct Pass {
    PassPoint rise, peak, set;
    // The part of the pass where the satellite is sunlit while the observer's
    // sky is dark (Sun below -6°): only then can it be seen.
    bool visible;  // a visible part exists and reaches at least 10° up
    std::optional<PassPoint> visibleStart, visibleEnd;
    double visibleMaxAltDeg;
    double brightestMagnitude;
};

// Passes that are still above the horizon at jd0 or rise before jd1, searched
// in 30-second steps (passes shorter than that are skipped).
std::vector<Pass> findPasses(const Sgp4& sat, const Geodetic& observer, double jd0, double jd1,
                             double stdMagnitude);

}  // namespace astro
