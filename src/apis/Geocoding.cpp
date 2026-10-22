#include "apis/Geocoding.hpp"

#include <stdexcept>

#include "http/HttpClient.hpp"

using nlohmann::json;

Geocoding::Geocoding() : cache_(std::chrono::hours(24)) {}

json Geocoding::search(const std::string& query) {
    // The API itself returns nothing for 1-character names.
    if (query.size() < 2) throw std::invalid_argument("search text must be at least 2 characters");
    if (auto cached = cache_.get(query)) return *cached;

    auto res = httpGet("https://geocoding-api.open-meteo.com/v1/search?count=8&language=en&format=json&name=" +
                       urlEncode(query));
    auto body = json::parse(res.body, nullptr, /*allow_exceptions=*/false);
    if (res.status != 200 || !body.is_object()) {
        std::string msg = "Geocoding API returned HTTP " + std::to_string(res.status);
        if (body.is_object() && body.contains("reason")) msg = body["reason"].get<std::string>();
        throw HttpError(res.status, msg);
    }

    json places = json::array();
    // "results" is absent when nothing matches.
    for (const auto& r : body.value("results", json::array())) {
        places.push_back({
            {"name", r.value("name", "")},
            {"region", r.value("admin1", "")},
            {"country", r.value("country", "")},
            {"lat", r.value("latitude", 0.0)},
            {"lon", r.value("longitude", 0.0)},
        });
    }
    cache_.put(query, places);
    return places;
}
