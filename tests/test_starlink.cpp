#include <doctest.h>

#include "astro/tle.hpp"
#include "services/Starlink.hpp"

using namespace astro;

namespace {

SatelliteSet sampleSet() {
    // Real Starlink TLEs (via SatNOGS) from October 2026.
    auto tles = parseTleFile(
        "STARLINK-3100\n"
        "1 49144U 21082Q   26295.16668980  .00038120  00000-0  22380-2 0  9994\n"
        "2 49144  70.0014  83.1836 0003596 259.3597  48.0136 15.11538324  5750\n"
        "STARLINK-4410\n"
        "1 53204U 22084R   26295.13490705 -.00002025  00000-0 -53839-4 0  9996\n"
        "2 53204  97.4042 359.3313 0002149  98.9058 261.2429 15.36976873234510\n"
        "STARLINK-4400\n"
        "1 53468U 22099D   26294.89363771  .00002503  00000-0  79843-4 0  9990\n"
        "2 53468  97.2868  48.1858 0001370  88.9613 271.1787 15.33441765230094\n");
    SatelliteSet set{{}, 0, "test"};
    for (const auto& t : tles) set.satellites.emplace_back(t);
    return set;
}

}  // namespace

TEST_CASE("starlinkReport counts and groups satellites") {
    auto set = sampleSet();
    double now = 1792670400;  // 2026-10-22 12:00 UTC
    auto report = starlinkReport(set, 52.23, 21.01, now);
    CHECK(report["counts"]["total"] == 3);
    CHECK(report["sky_dark"] == false);  // noon in Warsaw
    CHECK(report["counts"]["visible"] == 0);
    CHECK(report["satellites"].size() == report["counts"]["above_horizon"].get<size_t>());

    // Newest launch first: 2022-099, 2022-084, 2021-082.
    const auto& recent = report["recent_launches"];
    REQUIRE(recent.size() == 3);
    CHECK(recent[0]["launch"] == "2022-099");
    CHECK(recent[2]["launch"] == "2021-082");
    CHECK(recent[0]["train"] == false);  // ~530 km: already at its working altitude
}

TEST_CASE("starlinkReport sees satellites overhead over a whole day") {
    auto set = sampleSet();
    // Polar orbits pass over every latitude, so within a day some satellite rises.
    int seen = 0;
    for (int m = 0; m < 24 * 60; m += 5) {
        seen += starlinkReport(set, 52.23, 21.01, 1792670400 + m * 60.0)["counts"]["above_horizon"].get<int>();
    }
    CHECK(seen > 0);
}
