#include "services/Starlink.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <tuple>

#include "astro/passes.hpp"
#include "astro/sun_moon.hpp"
#include "astro/time.hpp"
#include "services/JsonUtil.hpp"
#include "services/SkyQuality.hpp"

using nlohmann::json;
using namespace astro;

namespace {

constexpr double kMinVisibleAltDeg = 10;
constexpr double kDarkSunAltDeg = -6;
constexpr double kNakedEyeMag = 6;
constexpr double kEarthRadiusKm = 6378.137;
// Starlinks are released around 300 km and climb to ~550 km over a few weeks;
// while still low they fly in a bright line, the "train".
constexpr double kTrainMaxAltKm = 450;
constexpr int kRecentLaunches = 3;

// "21082Q" -> "2021-082" (year, launch number of that year; the letter is the piece).
std::string launchOf(const std::string& designator) {
    if (designator.size() < 5) return "";
    int yy = std::stoi(designator.substr(0, 2));
    return std::to_string(yy < 57 ? 2000 + yy : 1900 + yy) + "-" + designator.substr(2, 3);
}

struct LaunchStats {
    int satellites = 0, aboveHorizon = 0, visible = 0;
    double altSumKm = 0;
};

}  // namespace

json starlinkReport(const SatelliteSet& set, double lat, double lon, double nowUnix, const Forecast* forecast) {
    double jd = jdFromUnix(nowUnix);
    Geodetic observer{lat, lon, 0};
    bool dark = sunHorizontal(jd, lat, lon).altDeg <= kDarkSunAltDeg;
    const HourlyWeather* w = forecast ? weatherAt(*forecast, nowUnix) : nullptr;
    bool cloudy = w && cloudBlocking(*w) >= kMaxCloudBlocking;

    std::map<std::string, LaunchStats> launches;
    json above = json::array();
    int total = 0, aboveHorizon = 0, sunlitAbove = 0, visible = 0;

    for (const auto& sat : set.satellites) {
        StateVector state;
        try {
            state = sat.at(jd);
        } catch (const Sgp4Error&) {
            continue;  // decayed since its TLE was published
        }
        ++total;
        std::string launch = launchOf(sat.tle().intlDesignator);
        auto& ls = launches[launch];
        ++ls.satellites;
        ls.altSumKm += state.r.norm() - kEarthRadiusKm;

        Vec3 ecef = temeToEcef(state.r, jd);
        auto look = lookAngles(ecef, observer);
        if (look.h.altDeg <= 0) continue;

        auto v = viewSatellite(sat, jd, observer, kStarlinkStdMagnitude);
        bool isVisible = dark && !cloudy && v.sunlit && look.h.altDeg >= kMinVisibleAltDeg && v.magnitude <= kNakedEyeMag;
        ++aboveHorizon;
        ++ls.aboveHorizon;
        if (v.sunlit) ++sunlitAbove;
        if (isVisible) {
            ++visible;
            ++ls.visible;
        }
        above.push_back({
            {"name", sat.tle().name},
            {"launch", launch},
            {"alt", round1(look.h.altDeg)},
            {"az", round1(look.h.azDeg)},
            {"sunlit", v.sunlit},
            {"visible", isVisible},
            {"magnitude", round1(v.magnitude)},
        });
    }

    // The newest launches, by year then launch number.
    std::vector<std::string> names;
    for (const auto& [name, stats] : launches) {
        if (!name.empty()) names.push_back(name);
    }
    std::sort(names.rbegin(), names.rend());
    json recent = json::array();
    for (int i = 0; i < kRecentLaunches && i < int(names.size()); ++i) {
        const auto& ls = launches[names[i]];
        double meanAlt = ls.altSumKm / ls.satellites;
        recent.push_back({
            {"launch", names[i]},
            {"satellites", ls.satellites},
            {"mean_alt_km", std::lround(meanAlt)},
            {"above_horizon", ls.aboveHorizon},
            {"visible", ls.visible},
            {"train", meanAlt < kTrainMaxAltKm},
        });
    }

    return {
        {"now", std::llround(nowUnix)},
        {"tle", {{"source", set.source}, {"fetched", std::llround(set.fetchedUnix)}}},
        {"sky_dark", dark},
        {"cloudy", cloudy},
        {"counts", {{"total", total}, {"above_horizon", aboveHorizon}, {"sunlit_above", sunlitAbove}, {"visible", visible}}},
        {"recent_launches", recent},
        {"satellites", above},
    };
}
