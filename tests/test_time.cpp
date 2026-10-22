#include <doctest.h>

#include "astro/coords.hpp"
#include "astro/time.hpp"

using namespace astro;

TEST_CASE("Julian Date from Unix time") {
    CHECK(jdFromUnix(0) == doctest::Approx(2440587.5));
    CHECK(jdFromUnix(946728000) == doctest::Approx(kJ2000));  // 2000-01-01 12:00 UTC
    CHECK(unixFromJd(jdFromUnix(1761134400)) == doctest::Approx(1761134400));
}

TEST_CASE("Greenwich mean sidereal time (Meeus examples 12.a and 12.b)") {
    CHECK(gmstDeg(2446895.5) == doctest::Approx(197.693195).epsilon(1e-8));
    CHECK(gmstDeg(2446896.30625) == doctest::Approx(128.7378734).epsilon(1e-8));
}

TEST_CASE("Equatorial to horizontal (Meeus example 13.b, Venus from Washington)") {
    // 1987-04-10 19:21 UT; apparent sidereal time 8h34m56.853s, observer 38°55'17"N 77°03'56"W.
    Equatorial venus{347.3193375, -6.719892};
    auto h = equatorialToHorizontal(venus, 128.736888 - 77.065556, 38.921389);
    CHECK(h.altDeg == doctest::Approx(15.1249).epsilon(1e-4));
    // Meeus measures azimuth from the south: 68.0337° there is 248.0337° from north.
    CHECK(h.azDeg == doctest::Approx(248.0337).epsilon(1e-4));
}

TEST_CASE("Compass points") {
    CHECK(std::string(compassPoint(0)) == "N");
    CHECK(std::string(compassPoint(359)) == "N");
    CHECK(std::string(compassPoint(90)) == "E");
    CHECK(std::string(compassPoint(135)) == "SE");
    CHECK(std::string(compassPoint(260)) == "W");
}
