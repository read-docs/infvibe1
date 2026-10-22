#include <doctest.h>

#include <cmath>
#include <string>
#include <vector>

#include "astro/passes.hpp"
#include "astro/sgp4.hpp"
#include "astro/time.hpp"
#include "astro/tle.hpp"
#include "services/Iss.hpp"

using namespace astro;

#include "sgp4_vectors.inc"

TEST_CASE("TLE parsing (ISS)") {
    auto t = parseTle("1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927",
                      "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537", "ISS (ZARYA)");
    CHECK(t.name == "ISS (ZARYA)");
    CHECK(t.catalogNumber == 25544);
    CHECK(t.intlDesignator == "98067A");
    // 2008 day 264.51782528 = 2008-09-20 12:25:40 UT.
    CHECK(t.epochJd == doctest::Approx(2454730.01782528).epsilon(1e-12));
    CHECK(t.bstar == doctest::Approx(-0.11606e-4));
    CHECK(t.eccentricity == doctest::Approx(0.0006703));
    CHECK(t.meanMotionRevPerDay == doctest::Approx(15.72125391));
}

TEST_CASE("TLE file parsing skips junk and keeps names") {
    auto tles = parseTleFile(
        "ISS (ZARYA)\r\n"
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927\r\n"
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537\r\n"
        "garbage\n"
        "1 too short\n"
        "2 too short\n");
    REQUIRE(tles.size() == 1);
    CHECK(tles[0].name == "ISS (ZARYA)");
}

TEST_CASE("SGP4 matches Vallado's verification vectors to a metre") {
    int checked = 0;
    for (const auto& c : kSgp4Cases) {
        CAPTURE(std::string(c.line1).substr(2, 5));
        Sgp4 sat(parseTle(c.line1, c.line2));
        for (const auto& e : c.expected) {
            CAPTURE(e.t);
            auto s = sat.propagate(e.t);
            CHECK(std::abs(s.r.x - e.x) < 1e-3);
            CHECK(std::abs(s.r.y - e.y) < 1e-3);
            CHECK(std::abs(s.r.z - e.z) < 1e-3);
            CHECK(std::abs(s.v.x - e.vx) < 1e-6);
            CHECK(std::abs(s.v.y - e.vy) < 1e-6);
            CHECK(std::abs(s.v.z - e.vz) < 1e-6);
            ++checked;
        }
    }
    CHECK(checked > 100);
}

TEST_CASE("SGP4 rejects deep-space orbits") {
    // Molniya 2-14: a 12-hour orbit.
    auto molniya = parseTle("1 08195U 75081A   06176.33215444  .00000099  00000-0  11873-3 0   813",
                            "2 08195  64.1586 279.0717 6877146 264.7651  20.2257  2.00491383225656");
    CHECK_THROWS_AS(Sgp4{molniya}, Sgp4Error);
}

TEST_CASE("ISS pass over Warsaw matches PyEphem") {
    auto tle = parseTle("1 25544U 98067A   26294.95113894  .00010428  00000-0  19720-3 0  9990",
                        "2 25544  51.6330  32.7943 0006789 293.2617  66.7657 15.48983994591404");
    Sgp4 iss(tle);
    Geodetic warsaw{52.23, 21.01, 0};
    double start = jdFromUnix(1792723800);  // 2026-10-23 02:50 UTC
    auto passes = findPasses(iss, warsaw, start, start + 0.05, kIssStdMagnitude);
    REQUIRE(passes.size() == 1);
    const auto& p = passes[0];
    // Reference: PyEphem's next_pass with the same TLE (rise/set at 0°, no refraction).
    CHECK(unixFromJd(p.rise.jd) == doctest::Approx(1792724200.3).epsilon(3e-9));  // ±5 s
    CHECK(unixFromJd(p.peak.jd) == doctest::Approx(1792724527.9).epsilon(3e-9));
    CHECK(unixFromJd(p.set.jd) == doctest::Approx(1792724856.9).epsilon(3e-9));
    CHECK(p.rise.azDeg == doctest::Approx(248.46).epsilon(1e-3));
    CHECK(p.peak.altDeg == doctest::Approx(61.715).epsilon(1e-3));
    CHECK(p.set.azDeg == doctest::Approx(80.94).epsilon(1e-3));
    // A dark morning sky: the ISS shows once it leaves Earth's shadow, just after the peak.
    CHECK(p.visible);
    REQUIRE(p.visibleStart);
    CHECK(p.visibleStart->jd > p.peak.jd);
    CHECK(p.brightestMagnitude < -3);
}

TEST_CASE("Earth-fixed conversions round-trip") {
    Geodetic g{52.23, 21.01, 420};
    auto back = ecefToGeodetic(geodeticToEcef(g));
    CHECK(back.latDeg == doctest::Approx(g.latDeg).epsilon(1e-9));
    CHECK(back.lonDeg == doctest::Approx(g.lonDeg).epsilon(1e-9));
    CHECK(back.altKm == doctest::Approx(g.altKm).epsilon(1e-6));
    // Straight overhead.
    auto look = lookAngles(geodeticToEcef(g), {52.23, 21.01, 0});
    CHECK(look.h.altDeg == doctest::Approx(90).epsilon(1e-6));
    CHECK(look.rangeKm == doctest::Approx(420).epsilon(1e-6));
}

TEST_CASE("issPasses marks a visible pass under clouds as not clear") {
    auto tle = parseTle("1 25544U 98067A   26294.95113894  .00010428  00000-0  19720-3 0  9990",
                        "2 25544  51.6330  32.7943 0006789 293.2617  66.7657 15.48983994591404");
    Sgp4 iss(tle);
    double start = 1792723800;  // 2026-10-23 02:50 UTC; the visible pass starts ~03:02
    Forecast f{"GMT", 0, {}};
    for (int i = -2; i < 4; ++i) f.hours.push_back({start - 1800 + i * 3600.0, 100, 100, 0, 0, 24000, 90, 0});
    auto out = issPasses(iss, {52.23, 21.01, 0}, start, 0.05, &f);
    REQUIRE(out["passes"].size() == 1);
    CHECK(out["passes"][0]["visible"] == true);
    CHECK(out["passes"][0]["clear"] == false);
    CHECK(out["passes"][0]["cloud"] == 100);

    // Without a forecast there is no cloud information at all.
    auto noWeather = issPasses(iss, {52.23, 21.01, 0}, start, 0.05, nullptr);
    CHECK_FALSE(noWeather["passes"][0].contains("clear"));
}
