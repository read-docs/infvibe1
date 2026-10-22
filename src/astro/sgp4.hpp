#pragma once

#include <stdexcept>

#include "astro/coords.hpp"
#include "astro/tle.hpp"

// SGP4 orbit propagator for near-Earth satellites (orbital period under 225
// minutes, which covers the ISS and every Starlink satellite). It follows
// Vallado, Crawford, Hujsak & Kelso, "Revisiting Spacetrack Report #3" (2006),
// with the WGS-72 constants TLEs are generated with. Deep-space orbits (SDP4)
// are not supported.
namespace astro {

// Position (km) and velocity (km/s) in the TEME frame: Earth-centred, true
// equator, mean equinox of date.
struct StateVector {
    Vec3 r;
    Vec3 v;
};

struct Sgp4Error : std::runtime_error {
    using std::runtime_error::runtime_error;
};

class Sgp4 {
public:
    // Throws Sgp4Error for deep-space orbits and invalid elements.
    explicit Sgp4(const Tle& tle);

    // State at minutesSinceEpoch after the TLE epoch. Throws Sgp4Error once
    // the model breaks down (e.g. the satellite has decayed).
    StateVector propagate(double minutesSinceEpoch) const;

    // State at a Julian Date.
    StateVector at(double jd) const { return propagate((jd - epochJd_) * 1440.0); }

    const Tle& tle() const { return tle_; }
    double periodMinutes() const;

private:
    Tle tle_;
    double epochJd_;
    // Initialised elements and secular/drag coefficients, named as in Vallado's code.
    double ecco_, inclo_, nodeo_, argpo_, mo_, no_, bstar_;
    double ao_, con41_, x1mth2_, x7thm1_, cosio_, sinio_, eta_;
    double cc1_, cc4_, cc5_, d2_, d3_, d4_, delmo_, sinmao_;
    double mdot_, argpdot_, nodedot_, nodecf_, omgcof_, xmcof_, t2cof_, t3cof_, t4cof_, t5cof_;
    double xlcof_, aycof_;
    bool isimp_;
};

}  // namespace astro
