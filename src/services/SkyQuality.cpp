#include "services/SkyQuality.hpp"

#include <algorithm>
#include <cmath>
#include <optional>

#include "astro/sun_moon.hpp"
#include "astro/time.hpp"
#include "services/JsonUtil.hpp"

using nlohmann::json;
using namespace astro;

namespace {

double clamp01(double x) { return std::clamp(x, 0.0, 1.0); }

}  // namespace

double cloudBlocking(const HourlyWeather& w) {
    double clear = (1 - clamp01(w.cloudLow / 100)) * (1 - 0.8 * clamp01(w.cloudMid / 100)) *
                   (1 - 0.5 * clamp01(w.cloudHigh / 100));
    return 1 - clear;
}

int hourScore(const HourlyWeather& w, double sunAltDeg, double moonAltDeg, double moonIllumination) {
    if (sunAltDeg > -6) return 0;  // civil twilight or daylight: too bright

    double score = 100 * (1 - cloudBlocking(w));
    score -= 15 * (1 - clamp01(w.visibilityM / 24000));  // haze
    if (w.humidity > 85) score -= 10;                    // dew and mist
    score -= 20 * clamp01(w.precipProbability / 100);
    if (moonAltDeg > 0) score -= 25 * moonIllumination;  // moonlight washes out faint stars

    // Faint objects need astronomical night (Sun below -18°); in nautical and
    // astronomical twilight only the bright planets and stars show, so the score is scaled down.
    double darkness = clamp01((-6 - sunAltDeg) / 12);
    score *= 0.5 + 0.5 * darkness;
    return int(std::lround(std::clamp(score, 0.0, 100.0)));
}

json skyReport(const Forecast& forecast, double lat, double lon, double nowUnix) {
    double jdNow = jdFromUnix(nowUnix);
    auto sunAlt = [&](double jd) { return sunHorizontal(jd, lat, lon).altDeg; };
    auto moonAlt = [&](double jd) { return moonHorizontal(jd, lat, lon).altDeg; };

    Night night = tonight(jdNow, lat, lon);
    double start = night.start, end = night.end;

    json twilight = json::object();
    const std::pair<const char*, double> levels[] = {{"civil", -6}, {"nautical", -12}, {"astronomical", -18}};
    for (const auto& [name, altDeg] : levels) {
        auto xs = findCrossings(sunAlt, start, end, altDeg);
        twilight[name] = {{"dusk", unixOrNull(firstCrossingAfter(xs, start, false))},
                          {"dawn", unixOrNull(lastCrossingBefore(xs, end, true))}};
    }

    json hours = json::array();
    json best = nullptr;
    double firstHour = std::floor(unixFromJd(start) / 3600) * 3600;
    for (const auto& w : forecast.hours) {
        if (w.time < firstHour || w.time > unixFromJd(end)) continue;
        double jd = jdFromUnix(w.time);
        double sAlt = sunAlt(jd);
        double mAlt = moonAlt(jd);
        int score = hourScore(w, sAlt, mAlt, moonPhase(jd).illumination);
        bool past = w.time + 3600 <= nowUnix;
        hours.push_back({
            {"time", std::llround(w.time)},
            {"score", score},
            {"past", past},
            {"cloud_cover", w.cloudCover},
            {"cloud_low", w.cloudLow},
            {"cloud_mid", w.cloudMid},
            {"cloud_high", w.cloudHigh},
            {"visibility_km", std::round(w.visibilityM / 100) / 10},
            {"humidity", w.humidity},
            {"precip_probability", w.precipProbability},
            {"sun_alt", std::round(sAlt * 10) / 10},
            {"moon_alt", std::round(mAlt * 10) / 10},
        });
        // Ties go to the earlier hour.
        if (!past && score > 0 && (best.is_null() || score > best["score"].get<int>())) {
            best = {{"time", std::llround(w.time)}, {"score", score}};
        }
    }

    auto moonXs = findCrossings(moonAlt, jdNow, jdNow + 1.2, kRiseSetAltDeg);
    auto phase = moonPhase(jdNow);

    return {
        {"location", {{"lat", lat}, {"lon", lon}, {"timezone", forecast.timezone},
                      {"utc_offset_seconds", forecast.utcOffsetSeconds}}},
        {"now", std::llround(nowUnix)},
        {"sun", skyPosition(sunHorizontal(jdNow, lat, lon))},
        {"moon", {
            {"position", skyPosition(moonHorizontal(jdNow, lat, lon))},
            {"illumination", std::round(phase.illumination * 1000) / 1000},
            {"phase", phase.name},
            {"waxing", phase.waxing},
            {"rise", unixOrNull(firstCrossingAfter(moonXs, jdNow, true))},
            {"set", unixOrNull(firstCrossingAfter(moonXs, jdNow, false))},
        }},
        {"night", {
            {"sunset", night.polar ? json(nullptr) : unixOrNull(start)},
            {"sunrise", night.polar ? json(nullptr) : unixOrNull(end)},
            {"polar", night.polar ? json(night.polar) : json(nullptr)},
            {"twilight", twilight},
        }},
        {"hours", hours},
        {"best", best},
    };
}
