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

}  // namespace

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
    bool darkNow = sunHorizontal(jdNow, lat, lon).altDeg <= kDarkSunAltDeg;
    bool clearNow = clear(jdNow);

    auto describe = [&](const char* name, const std::function<Horizontal(double)>& horizontal,
                        double riseSetAltDeg, double mag) {
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
        };
    };

    json bodies = json::array();

    auto phase = moonPhase(jdNow);
    json moon = describe("Moon", [&](double jd) { return moonHorizontal(jd, lat, lon); }, kRiseSetAltDeg,
                         moonMagnitude(phase.illumination));
    moon["distance_km"] = std::lround(moonPosition(jdNow).distanceKm);
    moon["illumination"] = std::round(phase.illumination * 1000) / 1000;
    bodies.push_back(moon);

    for (Planet p : kPlanets) {
        auto pos = planetPosition(p, jdNow);
        json body = describe(planetName(p), [&](double jd) { return planetHorizontal(p, jd, lat, lon); },
                             kPlanetRiseSetAltDeg, pos.magnitude);
        body["distance_au"] = std::round(pos.distanceAu * 1000) / 1000;
        body["elongation"] = round1(pos.elongationDeg);
        bodies.push_back(body);
    }

    return {{"now", std::llround(nowUnix)}, {"weather", forecast != nullptr}, {"bodies", bodies}};
}
