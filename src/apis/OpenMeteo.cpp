#include "apis/OpenMeteo.hpp"

#include <cstdio>
#include <nlohmann/json.hpp>

#include "http/HttpClient.hpp"

using nlohmann::json;

namespace {

// Hourly values can be null when a model has no data for that hour.
double valueAt(const json& hourly, const char* field, size_t i, double fallback) {
    const auto& arr = hourly.at(field);
    return i < arr.size() && arr[i].is_number() ? arr[i].get<double>() : fallback;
}

}  // namespace

const HourlyWeather* weatherAt(const Forecast& f, double unixTime) {
    for (const auto& h : f.hours) {
        if (unixTime >= h.time && unixTime < h.time + 3600) return &h;
    }
    return nullptr;
}

OpenMeteo::OpenMeteo() : cache_(std::chrono::minutes(30)) {}

Forecast OpenMeteo::forecast(double lat, double lon) {
    // Two decimals is ~1 km, far finer than the weather model's grid, so nearby
    // requests share one cache entry and one upstream call.
    char coords[64];
    std::snprintf(coords, sizeof coords, "latitude=%.2f&longitude=%.2f", lat, lon);
    if (auto cached = cache_.get(coords)) return *cached;

    auto res = httpGet(std::string("https://api.open-meteo.com/v1/forecast?") + coords +
                       "&hourly=cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
                       "visibility,relative_humidity_2m,precipitation_probability"
                       "&timezone=auto&timeformat=unixtime&forecast_days=4");
    auto body = json::parse(res.body, nullptr, /*allow_exceptions=*/false);
    if (res.status != 200 || !body.is_object() || !body.contains("hourly")) {
        // Open-Meteo error bodies look like {"error":true,"reason":"..."}.
        std::string msg = "Open-Meteo returned HTTP " + std::to_string(res.status);
        if (body.is_object() && body.contains("reason")) msg = body["reason"].get<std::string>();
        throw HttpError(res.status, msg);
    }

    Forecast f;
    f.timezone = body.value("timezone", "GMT");
    f.utcOffsetSeconds = body.value("utc_offset_seconds", 0);
    const auto& h = body["hourly"];
    for (size_t i = 0; i < h.at("time").size(); ++i) {
        f.hours.push_back({
            h["time"][i].get<double>(),
            valueAt(h, "cloud_cover", i, 0),
            valueAt(h, "cloud_cover_low", i, 0),
            valueAt(h, "cloud_cover_mid", i, 0),
            valueAt(h, "cloud_cover_high", i, 0),
            valueAt(h, "visibility", i, 24000),
            valueAt(h, "relative_humidity_2m", i, 0),
            valueAt(h, "precipitation_probability", i, 0),
        });
    }
    cache_.put(coords, f);
    return f;
}
