#include <doctest.h>

#include "services/Aurora.hpp"

TEST_CASE("Geomagnetic latitude") {
    // On the dipole axis and its antipode.
    CHECK(geomagneticLatitude(80.8, -72.8) == doctest::Approx(90));
    CHECK(geomagneticLatitude(-80.8, 107.2) == doctest::Approx(-90));
    // Europe sits nearer the magnetic equator than North America at the same latitude.
    double warsaw = geomagneticLatitude(52.23, 21.01);
    double winnipeg = geomagneticLatitude(49.9, -97.1);
    CHECK(warsaw == doctest::Approx(50.4).epsilon(0.02));
    CHECK(winnipeg > warsaw + 5);
}

TEST_CASE("Aurora chance by Kp") {
    double tromso = geomagneticLatitude(69.65, 18.96);  // ~67°: under the oval
    CHECK(auroraChance(1, tromso) == "overhead");
    double warsaw = geomagneticLatitude(52.23, 21.01);
    CHECK(auroraChance(2, warsaw) == "none");
    CHECK(auroraChance(5, warsaw) == "horizon");
    CHECK(auroraChance(9, warsaw) == "overhead");
    CHECK(auroraChance(-1, warsaw) == "none");  // no data
}

TEST_CASE("auroraReport combines Kp, darkness and clouds") {
    double noon = 1792670400;  // 2026-10-22 12:00 UTC
    KpData kp;
    for (int i = -8; i < 24; ++i) kp.threeHour.push_back({noon + i * 3 * 3600.0, 6.0, "predicted"});
    kp.current = 5.67;

    Forecast clear{"GMT", 0, {}};
    for (int i = 0; i < 72; ++i) clear.hours.push_back({noon - 12 * 3600 + i * 3600.0, 0, 0, 0, 0, 24000, 50, 0});

    auto report = auroraReport(kp, &clear, 52.23, 21.01, noon);
    CHECK(report["location"]["look_towards"] == "north");
    CHECK(report["kp_needed"]["horizon"].get<double>() == doctest::Approx(4.8).epsilon(0.05));
    CHECK(report["tonight"]["verdict"] == "go");
    CHECK(report["tonight"]["best"]["chance"] == "horizon");
    CHECK(report["now"]["kp"] == 5.67);

    Forecast overcast = clear;
    for (auto& h : overcast.hours) h.cloudLow = 100;
    CHECK(auroraReport(kp, &overcast, 52.23, 21.01, noon)["tonight"]["verdict"] == "cloudy");

    // Southern hemisphere looks south.
    CHECK(auroraReport(kp, &clear, -42.9, 147.3, noon)["location"]["look_towards"] == "south");
}
