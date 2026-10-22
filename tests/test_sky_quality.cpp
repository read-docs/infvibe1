#include <doctest.h>

#include "services/SkyQuality.hpp"

namespace {

HourlyWeather clearSky(double time = 0) { return {time, 0, 0, 0, 0, 24000, 50, 0}; }

// Hourly clear-sky forecast covering three days from startUnix.
Forecast clearForecast(double startUnix) {
    Forecast f{"GMT", 0, {}};
    for (int i = 0; i < 72; ++i) f.hours.push_back(clearSky(startUnix + i * 3600));
    return f;
}

}  // namespace

TEST_CASE("hourScore") {
    SUBCASE("clear dark moonless sky is perfect") { CHECK(hourScore(clearSky(), -30, -10, 1.0) == 100); }
    SUBCASE("daylight and civil twilight score zero") {
        CHECK(hourScore(clearSky(), 20, -10, 0) == 0);
        CHECK(hourScore(clearSky(), -5, -10, 0) == 0);
    }
    SUBCASE("twilight halves the score at -6 and fades in by -18") {
        CHECK(hourScore(clearSky(), -6, -10, 0) == 50);
        CHECK(hourScore(clearSky(), -12, -10, 0) == 75);
        CHECK(hourScore(clearSky(), -18, -10, 0) == 100);
    }
    SUBCASE("overcast low cloud blocks everything") {
        auto w = clearSky();
        w.cloudLow = 100;
        CHECK(hourScore(w, -30, -10, 0) == 0);
    }
    SUBCASE("high cirrus blocks only half") {
        auto w = clearSky();
        w.cloudHigh = 100;
        CHECK(hourScore(w, -30, -10, 0) == 50);
    }
    SUBCASE("a full Moon above the horizon costs 25 points") {
        CHECK(hourScore(clearSky(), -30, 20, 1.0) == 75);
        CHECK(hourScore(clearSky(), -30, 20, 0.5) == 88);  // 87.5 rounds up
    }
    SUBCASE("haze, humidity and rain chance") {
        auto w = clearSky();
        w.visibilityM = 12000;
        w.humidity = 90;
        w.precipProbability = 50;
        CHECK(hourScore(w, -30, -10, 0) == 73);  // 100 - 7.5 haze - 10 humidity - 10 rain
    }
}

TEST_CASE("skyReport for an ordinary night (Warsaw, 2026-10-22 12:00 UTC)") {
    double now = 1792670400;
    auto report = skyReport(clearForecast(now - 12 * 3600), 52.23, 21.01, now);

    const auto& night = report["night"];
    REQUIRE(night["polar"].is_null());
    double sunset = night["sunset"], sunrise = night["sunrise"];
    CHECK(sunset > now);
    CHECK(sunrise > sunset);
    CHECK((sunrise - sunset) / 3600 == doctest::Approx(13.5).epsilon(0.03));  // late October: ~13.5 h of night

    double civil = night["twilight"]["civil"]["dusk"], astro = night["twilight"]["astronomical"]["dusk"];
    CHECK(civil > sunset);
    CHECK(astro > civil);

    const auto& hours = report["hours"];
    REQUIRE(hours.size() >= 13);
    CHECK(hours.front()["time"].get<double>() <= sunset);
    CHECK(hours.back()["time"].get<double>() <= sunrise);
    REQUIRE(report["best"].is_object());
    CHECK(report["best"]["score"].get<int>() > 0);
}

TEST_CASE("skyReport at the night's start counts the current hour as still ahead") {
    double now = 1792670400 + 5 * 3600 + 1800;  // 17:30 UTC, after sunset in Warsaw
    auto report = skyReport(clearForecast(now - 12 * 3600), 52.23, 21.01, now);
    CHECK(report["night"]["sunset"].get<double>() < now);
    for (const auto& h : report["hours"]) {
        CHECK(h["past"].get<bool>() == (h["time"].get<double>() + 3600 <= now));
    }
}

TEST_CASE("skyReport near the poles") {
    SUBCASE("midnight Sun in Tromsø") {
        double now = 1782043200;  // 2026-06-21 12:00 UTC
        auto report = skyReport(clearForecast(now), 69.65, 18.96, now);
        CHECK(report["night"]["polar"] == "day");
        CHECK(report["best"].is_null());
    }
    SUBCASE("polar night in Tromsø") {
        double now = 1797854400;  // 2026-12-21 12:00 UTC
        auto report = skyReport(clearForecast(now), 69.65, 18.96, now);
        CHECK(report["night"]["polar"] == "night");
        CHECK(report["best"].is_object());
    }
}
