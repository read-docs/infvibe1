#include "services/Iss.hpp"

#include <cmath>

#include "astro/passes.hpp"
#include "astro/time.hpp"
#include "services/JsonUtil.hpp"
#include "services/SkyQuality.hpp"

using nlohmann::json;
using namespace astro;

namespace {

json passPoint(const PassPoint& p) {
    return {{"time", std::llround(unixFromJd(p.jd))},
            {"alt", round1(p.altDeg)},
            {"az", round1(p.azDeg)},
            {"direction", compassPoint(p.azDeg)}};
}

}  // namespace

json issNow(const SatelliteSet& set, double nowUnix, const std::optional<Geodetic>& observer) {
    const Sgp4& sat = set.satellites.front();
    double jd = jdFromUnix(nowUnix);
    // Any observer works for the subpoint; the look angles are only reported when one was given.
    auto v = viewSatellite(sat, jd, observer.value_or(Geodetic{0, 0, 0}), kIssStdMagnitude);
    json out = {
        {"time", std::llround(nowUnix)},
        {"lat", std::round(v.subpoint.latDeg * 1e4) / 1e4},
        {"lon", std::round(v.subpoint.lonDeg * 1e4) / 1e4},
        {"alt_km", round1(v.subpoint.altKm)},
        {"speed_kms", std::round(v.speedKmS * 1000) / 1000},
        {"period_min", round1(sat.periodMinutes())},
        {"sunlit", v.sunlit},
        {"tle", {{"epoch", unixOrNull(sat.tle().epochJd)},
                 {"source", set.source},
                 {"age_hours", round1((jd - sat.tle().epochJd) * 24)}}},
    };
    if (observer) {
        out["look"] = skyPosition(v.look.h);
        out["look"]["range_km"] = std::lround(v.look.rangeKm);
    }
    return out;
}

json issCheck(const Sgp4& sat, const LiveIssPosition& live) {
    double jd = jdFromUnix(live.unixTime);
    Vec3 ours = temeToEcef(sat.at(jd).r, jd);
    Vec3 theirs = geodeticToEcef({live.latDeg, live.lonDeg, live.altKm});
    Geodetic g = ecefToGeodetic(ours);
    return {
        {"source", "wheretheiss.at"},
        {"time", std::llround(live.unixTime)},
        {"live", {{"lat", live.latDeg}, {"lon", live.lonDeg}, {"alt_km", round1(live.altKm)}}},
        {"ours", {{"lat", g.latDeg}, {"lon", g.lonDeg}, {"alt_km", round1(g.altKm)}}},
        {"difference_km", std::round((ours - theirs).norm() * 100) / 100},
    };
}

json issTrack(const Sgp4& sat, double nowUnix, double minutes) {
    json points = json::array();
    for (double t = nowUnix - minutes * 60; t <= nowUnix + minutes * 60; t += 30) {
        auto g = subpoint(sat, jdFromUnix(t));
        points.push_back({{"time", std::llround(t)},
                          {"lat", std::round(g.latDeg * 1e3) / 1e3},
                          {"lon", std::round(g.lonDeg * 1e3) / 1e3}});
    }
    return {{"now", std::llround(nowUnix)}, {"points", points}};
}

json issPasses(const Sgp4& sat, const Geodetic& observer, double nowUnix, double days, const Forecast* forecast) {
    double jd = jdFromUnix(nowUnix);
    json out = json::array();
    for (const auto& p : findPasses(sat, observer, jd, jd + days, kIssStdMagnitude)) {
        json pass = {
            {"rise", passPoint(p.rise)},
            {"peak", passPoint(p.peak)},
            {"set", passPoint(p.set)},
            {"visible", p.visible},
        };
        if (p.visibleStart) {
            pass["visible_part"] = {{"start", passPoint(*p.visibleStart)},
                                    {"end", passPoint(*p.visibleEnd)},
                                    {"max_alt", round1(p.visibleMaxAltDeg)},
                                    {"magnitude", round1(p.brightestMagnitude)}};
            const HourlyWeather* w = forecast ? weatherAt(*forecast, unixFromJd(p.visibleStart->jd)) : nullptr;
            if (w) {
                double blocking = cloudBlocking(*w);
                pass["cloud"] = std::lround(blocking * 100);
                pass["clear"] = blocking < kMaxCloudBlocking;
            }
        }
        out.push_back(pass);
    }
    return {{"now", std::llround(nowUnix)}, {"passes", out}};
}
