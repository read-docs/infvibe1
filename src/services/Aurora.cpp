#include "services/Aurora.hpp"

#include <algorithm>
#include <cmath>
#include <string>

#include "astro/coords.hpp"
#include "astro/sun_moon.hpp"
#include "astro/time.hpp"
#include "services/JsonUtil.hpp"
#include "services/SkyQuality.hpp"

using nlohmann::json;
using namespace astro;

namespace {

constexpr double kPoleLat = 80.8, kPoleLon = -72.8;
// A rule of thumb fitted to NOAA's aurora "view line": at Kp 0 the oval's edge
// sits near 67° geomagnetic latitude and moves ~2° towards the equator per Kp
// step; from the ground the aurora shows low on the horizon ~7° beyond that.
constexpr double kOvalEdgeAtKp0 = 67, kOvalDegPerKp = 2, kHorizonReach = 7, kCameraReach = 10;
constexpr double kAuroraDarkSunAltDeg = -12;  // aurora is faint: needs nautical darkness

int rank(const std::string& chance) {
    if (chance == "overhead") return 3;
    if (chance == "horizon") return 2;
    if (chance == "camera") return 1;
    return 0;
}

// Kp of the 3-hour interval containing t, or -1.
double kpAt(const KpData& kp, double t) {
    for (const auto& p : kp.threeHour) {
        if (t >= p.time && t < p.time + 3 * 3600) return p.kp;
    }
    return -1;
}

double round2(double x) { return std::round(x * 100) / 100; }

}  // namespace

double geomagneticLatitude(double lat, double lon) {
    double s = sinDeg(lat) * sinDeg(kPoleLat) + cosDeg(lat) * cosDeg(kPoleLat) * cosDeg(lon - kPoleLon);
    return deg(std::asin(s));
}

std::string auroraChance(double kp, double geomagLat) {
    if (kp < 0) return "none";
    double edge = kOvalEdgeAtKp0 - kOvalDegPerKp * kp;
    double m = std::abs(geomagLat);
    if (m >= edge) return "overhead";
    if (m >= edge - kHorizonReach) return "horizon";
    if (m >= edge - kCameraReach) return "camera";
    return "none";
}

json auroraReport(const KpData& kp, const Forecast* forecast, double lat, double lon, double nowUnix) {
    double mlat = geomagneticLatitude(lat, lon);
    double m = std::abs(mlat);
    // Inverting the rule: the Kp at which the oval's edge (or the horizon view) reaches us.
    auto needed = [&](double reach) {
        return std::clamp((kOvalEdgeAtKp0 - reach - m) / kOvalDegPerKp, 0.0, 9.0);
    };

    json series = json::array();
    for (const auto& p : kp.threeHour) {
        if (p.time < nowUnix - 2 * 86400) continue;  // two days of history is plenty
        series.push_back({{"time", std::llround(p.time)}, {"kp", round2(p.kp)}, {"kind", p.kind},
                          {"chance", auroraChance(p.kp, mlat)}});
    }

    // Tonight, hour by hour.
    double jdNow = jdFromUnix(nowUnix);
    Night night = tonight(jdNow, lat, lon);
    json hours = json::array();
    json best = nullptr;
    int bestRank = -1;
    double bestCloud = 2;
    double maxKp = -1;
    if (!night.polar || std::string(night.polar) != "day") {
        double start = std::floor(unixFromJd(std::max(night.start, jdNow)) / 3600) * 3600;
        for (double t = start; t <= unixFromJd(night.end); t += 3600) {
            double sunAlt = sunHorizontal(jdFromUnix(t + 1800), lat, lon).altDeg;
            if (sunAlt > kAuroraDarkSunAltDeg) continue;
            double k = kpAt(kp, t + 1800);
            maxKp = std::max(maxKp, k);
            std::string chance = auroraChance(k, mlat);
            const HourlyWeather* w = forecast ? weatherAt(*forecast, t + 1800) : nullptr;
            double cloud = w ? cloudBlocking(*w) : -1;
            hours.push_back({{"time", std::llround(t)}, {"kp", round2(k)}, {"chance", chance},
                             {"cloud", w ? json(std::round(cloud * 100)) : json(nullptr)}});
            // Best: the strongest chance, then the clearest sky.
            int r = rank(chance);
            double c = w ? cloud : 0.5;
            if (r > bestRank || (r == bestRank && c < bestCloud)) {
                bestRank = r;
                bestCloud = c;
                best = hours.back();
            }
        }
    }

    // One overall verdict for tonight.
    std::string verdict;
    if (hours.empty()) verdict = "no_darkness";
    else if (bestRank >= 2 && (!forecast || bestCloud < kMaxCloudBlocking)) verdict = "go";
    else if (bestRank >= 2) verdict = "cloudy";
    else if (bestRank == 1) verdict = "camera";
    else verdict = "unlikely";

    return {
        {"location", {{"lat", lat}, {"lon", lon}, {"geomagnetic_lat", round1(mlat)},
                      {"look_towards", mlat >= 0 ? "north" : "south"}}},
        {"kp_needed", {{"overhead", round1(needed(0))}, {"horizon", round1(needed(kHorizonReach))}}},
        {"now", {{"kp", kp.current ? json(round2(*kp.current)) : json(nullptr)},
                 {"chance", auroraChance(kp.current.value_or(kpAt(kp, nowUnix)), mlat)},
                 {"dark", sunHorizontal(jdNow, lat, lon).altDeg <= kAuroraDarkSunAltDeg}}},
        {"forecast", series},
        {"tonight", {{"hours", hours}, {"best", best}, {"max_kp", round2(maxKp)}, {"verdict", verdict},
                     {"weather", forecast != nullptr}}},
    };
}
