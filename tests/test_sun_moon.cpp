#include <doctest.h>

#include "astro/sun_moon.hpp"
#include "astro/time.hpp"

using namespace astro;

TEST_CASE("Sun position (Meeus example 25.a, 1992-10-13 0h)") {
    double jd = 2448908.5;
    CHECK(sunEcliptic(jd).lonDeg == doctest::Approx(199.90895).epsilon(1e-6));
    auto eq = sunEquatorial(jd);
    CHECK(eq.raDeg == doctest::Approx(198.38083).epsilon(1e-6));
    CHECK(eq.decDeg == doctest::Approx(-7.78507).epsilon(1e-5));
    CHECK(sunDistanceKm(jd) / 149597870.7 == doctest::Approx(0.99766).epsilon(1e-5));
}

TEST_CASE("Moon position (Meeus example 47.a, 1992-04-12 0h)") {
    auto moon = moonPosition(2448724.5);
    // The tables are truncated, so allow ~0.01° instead of Meeus's full precision.
    CHECK(moon.ecl.lonDeg == doctest::Approx(133.162655).epsilon(1e-4));
    CHECK(moon.ecl.latDeg == doctest::Approx(-3.229126).epsilon(3e-3));
    CHECK(moon.distanceKm == doctest::Approx(368409.7).epsilon(1e-4));
    CHECK(moon.eq.raDeg == doctest::Approx(134.688470).epsilon(1e-4));
    CHECK(moon.eq.decDeg == doctest::Approx(13.768368).epsilon(1e-3));
}

TEST_CASE("Moon phase (Meeus example 48.a, 1992-04-12 0h)") {
    auto phase = moonPhase(2448724.5);
    CHECK(phase.illumination == doctest::Approx(0.6786).epsilon(1e-3));
    CHECK(phase.waxing);
    CHECK(std::string(phase.name) == "Waxing Gibbous");
}

TEST_CASE("findCrossings finds both directions and refines to a second") {
    // A fake "altitude" that is a sine wave with a 1-day period, crossing 0 at 0.25 and 0.75 days.
    auto alt = [](double jd) { return 10 * std::cos(2 * kPi * jd); };
    auto xs = findCrossings(alt, 0, 1, 0);
    REQUIRE(xs.size() == 2);
    CHECK_FALSE(xs[0].rising);
    CHECK(xs[0].jd == doctest::Approx(0.25).epsilon(2.0 / 86400));
    CHECK(xs[1].rising);
    CHECK(xs[1].jd == doctest::Approx(0.75).epsilon(2.0 / 86400));
}
