#include <doctest.h>

#include <string>

#include "astro/planets.hpp"
#include "services/Planets.hpp"

using namespace astro;

TEST_CASE("Venus position (Meeus example 33.a, 1992-12-20 0h)") {
    auto venus = planetPosition(Planet::Venus, 2448976.5);
    // JPL's approximate elements are good to about an arcminute for Venus.
    CHECK(venus.eq.raDeg == doctest::Approx(316.172725).epsilon(1e-4));   // ±0.03°
    CHECK(venus.eq.decDeg == doctest::Approx(-18.888011).epsilon(1.5e-3));  // ±0.03°
    CHECK(venus.distanceAu == doctest::Approx(0.910947).epsilon(1e-4));
    CHECK(venus.sunDistanceAu == doctest::Approx(0.724604).epsilon(1e-4));
    // Meeus 41.a gives the phase angle as 72.96°.
    CHECK(venus.phaseAngleDeg == doctest::Approx(72.96).epsilon(2e-3));
}

TEST_CASE("Planet magnitudes are in their usual ranges") {
    double jd = 2461336.0;  // 2026-10-22 12:00 UTC
    CHECK(planetPosition(Planet::Venus, jd).magnitude < -3.5);
    CHECK(planetPosition(Planet::Jupiter, jd).magnitude < -1.5);
    auto saturn = planetPosition(Planet::Saturn, jd).magnitude;
    CHECK(saturn > -0.5);
    CHECK(saturn < 1.5);
    CHECK(planetPosition(Planet::Uranus, jd).magnitude == doctest::Approx(5.7).epsilon(0.05));
    CHECK(planetPosition(Planet::Neptune, jd).magnitude == doctest::Approx(7.8).epsilon(0.05));
}

TEST_CASE("Inner planets never stray far from the Sun") {
    for (double jd = 2461000; jd < 2461400; jd += 7) {
        CHECK(planetPosition(Planet::Mercury, jd).elongationDeg < 28.5);
        CHECK(planetPosition(Planet::Venus, jd).elongationDeg < 47.5);
    }
}

TEST_CASE("planetsReport lists the Moon and seven planets") {
    double noon = 1792670400;  // 2026-10-22 12:00 UTC, broad daylight in Warsaw
    auto report = planetsReport(52.23, 21.01, noon, nullptr);
    const auto& bodies = report["bodies"];
    REQUIRE(bodies.size() == 8);
    CHECK(bodies[0]["name"] == "Moon");
    CHECK(bodies[7]["name"] == "Neptune");
    for (const auto& b : bodies) {
        CHECK_FALSE(b["visible_now"].get<bool>());  // daytime
        for (const auto& w : b["tonight"]) {
            CHECK(w["from"].get<double>() <= w["to"].get<double>());
            CHECK(w["from"].get<double>() > noon);
        }
    }
    CHECK_FALSE(bodies[7]["naked_eye"].get<bool>());  // Neptune needs a telescope
}

TEST_CASE("planetsReport hides planets behind clouds") {
    double noon = 1792670400;  // 2026-10-22 12:00 UTC
    Forecast f{"GMT", 0, {}};
    for (int i = 0; i < 72; ++i) {
        // Overcast except 20:00-23:00 UTC.
        bool gap = i >= 20 && i < 23;
        f.hours.push_back({noon - 12 * 3600 + i * 3600.0, 0, gap ? 0.0 : 100.0, 0, 0, 24000, 50, 0});
    }
    auto report = planetsReport(52.23, 21.01, noon, &f);
    CHECK(report["weather"] == true);
    // Saturn is high all evening, so the only clear window is the gap in the clouds.
    const auto& saturn = report["bodies"][5];
    REQUIRE(saturn["name"] == "Saturn");
    CHECK(saturn["high_tonight"] == true);
    REQUIRE(saturn["tonight"].size() == 1);
    double from = saturn["tonight"][0]["from"], to = saturn["tonight"][0]["to"];
    CHECK(from >= noon - 12 * 3600 + 20 * 3600);
    CHECK(to < noon - 12 * 3600 + 23 * 3600);

    // Fully overcast: high tonight, but no window at all.
    for (auto& h : f.hours) h.cloudLow = 100;
    auto cloudy = planetsReport(52.23, 21.01, noon, &f);
    CHECK(cloudy["bodies"][5]["high_tonight"] == true);
    CHECK(cloudy["bodies"][5]["tonight"].empty());
}

TEST_CASE("bodyVisibility") {
    SUBCASE("high in a dark clear sky is perfect") {
        auto v = bodyVisibility(60, 0, -30, 0, 0);
        CHECK(v.score == 100);
        CHECK(v.limit == nullptr);
    }
    SUBCASE("below 10 degrees it can't be seen") {
        auto v = bodyVisibility(8, -2, -30, 0, 0);
        CHECK(v.score == 0);
        CHECK(std::string(v.limit) == "too_low");
    }
    SUBCASE("low down counts for less") {
        CHECK(bodyVisibility(10, 0, -30, 0, 0).score == 40);
        CHECK(bodyVisibility(25, 0, -30, 0, 0).score == 70);
    }
    SUBCASE("bright planets show in twilight, faint ones need darkness") {
        CHECK(bodyVisibility(40, -4.2, -6, 0, 0).score == 100);  // Venus
        CHECK(bodyVisibility(40, -2.0, -8, 0, 0).score == 50);   // Jupiter, fading in
        auto uranus = bodyVisibility(40, 5.7, -8, 0, 0);
        CHECK(uranus.score == 0);
        CHECK(std::string(uranus.limit) == "too_bright");
        CHECK(bodyVisibility(40, 5.7, -21, 0, 0).score == 100);
    }
    SUBCASE("a few clouds dim it, a cloudy sky hides it") {
        CHECK(bodyVisibility(40, 0, -30, 0.3, 0).score == 70);
        auto v = bodyVisibility(40, 0, -30, 0.5, 0);
        CHECK(v.score == 0);
        CHECK(std::string(v.limit) == "clouds");
    }
    SUBCASE("moonlight dims only faint bodies") {
        CHECK(bodyVisibility(40, -2, -30, 0, 1.0).score == 100);
        auto neptune = bodyVisibility(40, 7.8, -30, 0, 1.0);
        CHECK(neptune.score == 50);
        CHECK(std::string(neptune.limit) == "moonlight");
    }
}

TEST_CASE("planetsReport rates each body hour by hour") {
    double noon = 1792670400;  // 2026-10-22 12:00 UTC, Warsaw
    Forecast f{"GMT", 0, {}};
    for (int i = 0; i < 72; ++i) {
        // Overcast except 20:00-23:00 UTC.
        bool gap = i >= 20 && i < 23;
        f.hours.push_back({noon - 12 * 3600 + i * 3600.0, 0, gap ? 0.0 : 100.0, 0, 0, 24000, 50, 0});
    }
    auto report = planetsReport(52.23, 21.01, noon, &f);
    for (const auto& b : report["bodies"]) {
        REQUIRE(b["hours"].size() >= 13);  // sunset to sunrise
        for (const auto& h : b["hours"]) {
            double t = h["time"];
            bool clear = t >= noon + 8 * 3600 && t < noon + 11 * 3600;
            if (!clear) CHECK(h["score"] == 0);
            if (h["alt"].get<double>() < 10) CHECK(h["score"] == 0);
        }
        // The best hour can only be in the gap in the clouds.
        if (b["best"].is_object()) {
            double t = b["best"]["time"];
            CHECK(t >= noon + 8 * 3600);
            CHECK(t < noon + 11 * 3600);
        }
    }
    const auto& saturn = report["bodies"][5];
    REQUIRE(saturn["best"].is_object());
    CHECK(saturn["best"]["score"].get<int>() > 50);

    // Without a forecast, clouds are ignored and the hours still come back.
    auto noWeather = planetsReport(52.23, 21.01, noon, nullptr);
    CHECK(noWeather["bodies"][5]["hours"].size() == saturn["hours"].size());
    CHECK(noWeather["bodies"][5]["best"]["score"].get<int>() >= saturn["best"]["score"].get<int>());
}
