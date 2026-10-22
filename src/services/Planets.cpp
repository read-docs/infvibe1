#include "services/Planets.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <optional>
#include <string>
#include <vector>

#include "astro/planets.hpp"
#include "astro/sun_moon.hpp"
#include "astro/time.hpp"
#include "services/JsonUtil.hpp"
#include "services/SkyQuality.hpp"

using nlohmann::json;
using namespace astro;

namespace {

constexpr double kMinAltDeg = 10;      // lower than this, haze and buildings usually hide things
constexpr double kDarkSunAltDeg = -6;  // end of civil twilight: bright planets show
constexpr double kNakedEyeMag = 6;     // faintest magnitude visible without optics
constexpr double kSampleDays = 5.0 / 1440;

// Moon magnitude from its phase angle (Allen, Astrophysical Quantities).
double moonMagnitude(double illumination) {
    double i = deg(std::acos(std::clamp(2 * illumination - 1, -1.0, 1.0)));
    return -12.73 + 0.026 * i + 4e-9 * std::pow(i, 4);
}

double clamp01(double x) { return std::clamp(x, 0.0, 1.0); }

}  // namespace

BodyVisibility bodyVisibility(double altDeg, double magnitude, double sunAltDeg, double cloudBlocking,
                              double moonGlow) {
    // Low down, the light crosses more air: dimmer and blurrier. Full marks from 40° up.
    double altitude = altDeg < kMinAltDeg ? 0 : 0.4 + 0.6 * clamp01((altDeg - kMinAltDeg) / 30);
    // Brighter bodies show earlier in twilight: Venus with the Sun 3° down, a
    // magnitude 2 planet only at -18°. The factor fades in over 6° around that point.
    double needSunAlt = std::clamp(-3 - 2.5 * (magnitude + 4), -18.0, -3.0);
    double darkness = clamp01((needSunAlt + 3 - sunAltDeg) / 6);
    // Like everywhere else in the app, only a mostly clear sky counts.
    double clouds = cloudBlocking >= kMaxCloudBlocking ? 0 : 1 - clamp01(cloudBlocking);
    // Moonlight drowns faint bodies (magnitude 3 and fainter), not bright planets.
    double moonlight = 1 - 0.5 * clamp01(moonGlow) * clamp01((magnitude - 3) / 3);

    double score = 100 * altitude * darkness * clouds * moonlight;
    const std::pair<double, const char*> factors[] = {
        {altitude, "too_low"}, {darkness, "too_bright"}, {clouds, "clouds"}, {moonlight, "moonlight"}};
    const auto& worst = *std::min_element(std::begin(factors), std::end(factors),
                                          [](const auto& a, const auto& b) { return a.first < b.first; });
    return {int(std::lround(score)), worst.first < 0.9 ? worst.second : nullptr};
}

json planetsReport(double lat, double lon, double nowUnix, const Forecast* forecast) {
    double jdNow = jdFromUnix(nowUnix);
    Night night = tonight(jdNow, lat, lon);

    // Hours the forecast doesn't cover count as clear rather than hiding everything.
    auto clear = [&](double jd) {
        const HourlyWeather* w = forecast ? weatherAt(*forecast, unixFromJd(jd)) : nullptr;
        return !w || cloudBlocking(*w) < kMaxCloudBlocking;
    };

    // The rest of tonight, sampled every 5 minutes. Darkness and clouds are the
    // same for every body, so they are worked out once.
    struct Sample {
        double jd;
        bool clear;
    };
    std::vector<Sample> darkTimes;
    if (!night.polar || std::string(night.polar) != "day") {
        for (double jd = std::max(night.start, jdNow); jd <= night.end; jd += kSampleDays) {
            if (sunHorizontal(jd, lat, lon).altDeg <= kDarkSunAltDeg) darkTimes.push_back({jd, clear(jd)});
        }
    }
    // Whole hours from sunset to sunrise, matching the /api/sky timeline. What
    // the Sun, clouds and Moon do each hour is the same for every body.
    struct Hour {
        double unix, jd, sunAlt, blocking, moonGlow;
        bool past;
    };
    std::vector<Hour> hours;
    if (!night.polar || std::string(night.polar) != "day") {
        double endUnix = unixFromJd(night.end);
        for (double t = std::floor(unixFromJd(night.start) / 3600) * 3600; t <= endUnix; t += 3600) {
            double jd = jdFromUnix(t);
            const HourlyWeather* w = forecast ? weatherAt(*forecast, t) : nullptr;
            double moonGlow = moonHorizontal(jd, lat, lon).altDeg > 0 ? moonPhase(jd).illumination : 0;
            hours.push_back({t, jd, sunHorizontal(jd, lat, lon).altDeg, w ? cloudBlocking(*w) : 0, moonGlow,
                             t + 3600 <= nowUnix});
        }
    }

    bool darkNow = sunHorizontal(jdNow, lat, lon).altDeg <= kDarkSunAltDeg;
    bool clearNow = clear(jdNow);

    auto describe = [&](const char* name, const std::function<Horizontal(double)>& horizontal,
                        double riseSetAltDeg, double mag, bool isMoon) {
        auto alt = [&](double jd) { return horizontal(jd).altDeg; };
        auto xs = findCrossings(alt, jdNow, jdNow + 1.2, riseSetAltDeg);
        auto now = horizontal(jdNow);

        // Clear stretches as [from, to] pairs; a cloudy hour splits them.
        json windows = json::array();
        bool highTonight = false;
        std::optional<double> from, to;
        for (const auto& s : darkTimes) {
            bool high = alt(s.jd) >= kMinAltDeg;
            highTonight = highTonight || high;
            if (high && s.clear) {
                if (!from) from = s.jd;
                to = s.jd;
            } else if (from) {
                windows.push_back({{"from", unixOrNull(from)}, {"to", unixOrNull(to)}});
                from.reset();
            }
        }
        if (from) windows.push_back({{"from", unixOrNull(from)}, {"to", unixOrNull(to)}});

        json hourly = json::array();
        json best = nullptr;
        for (const auto& h : hours) {
            auto pos = horizontal(h.jd);
            auto v = bodyVisibility(pos.altDeg, mag, h.sunAlt, h.blocking, isMoon ? 0 : h.moonGlow);
            hourly.push_back({{"time", std::llround(h.unix)}, {"score", v.score}, {"alt", round1(pos.altDeg)},
                              {"direction", compassPoint(pos.azDeg)},
                              {"limit", v.limit ? json(v.limit) : json(nullptr)}});
            // Ties go to the earlier hour.
            if (!h.past && v.score > 0 && (best.is_null() || v.score > best["score"].get<int>())) best = hourly.back();
        }

        bool nakedEye = mag <= kNakedEyeMag;
        return json{
            {"name", name},
            {"position", skyPosition(now)},
            {"magnitude", round1(mag)},
            {"naked_eye", nakedEye},
            {"up", now.altDeg > 0},
            {"visible_now", darkNow && clearNow && nakedEye && now.altDeg >= kMinAltDeg},
            {"rise", unixOrNull(firstCrossingAfter(xs, jdNow, true))},
            {"set", unixOrNull(firstCrossingAfter(xs, jdNow, false))},
            // high_tonight without any windows means clouds are in the way.
            {"high_tonight", highTonight},
            {"tonight", windows},
            {"hours", hourly},
            {"best", best},
        };
    };

    json bodies = json::array();

    auto phase = moonPhase(jdNow);
    json moon = describe("Moon", [&](double jd) { return moonHorizontal(jd, lat, lon); }, kRiseSetAltDeg,
                         moonMagnitude(phase.illumination), true);
    moon["distance_km"] = std::lround(moonPosition(jdNow).distanceKm);
    moon["illumination"] = std::round(phase.illumination * 1000) / 1000;
    bodies.push_back(moon);

    for (Planet p : kPlanets) {
        auto pos = planetPosition(p, jdNow);
        json body = describe(planetName(p), [&](double jd) { return planetHorizontal(p, jd, lat, lon); },
                             kPlanetRiseSetAltDeg, pos.magnitude, false);
        body["distance_au"] = std::round(pos.distanceAu * 1000) / 1000;
        body["elongation"] = round1(pos.elongationDeg);
        bodies.push_back(body);
    }

    return {{"now", std::llround(nowUnix)}, {"weather", forecast != nullptr}, {"bodies", bodies}};
}
