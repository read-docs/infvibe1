#include "apis/WhereTheIss.hpp"

#include <nlohmann/json.hpp>

#include "http/HttpClient.hpp"

WhereTheIss::WhereTheIss() : cache_(std::chrono::seconds(4)) {}

LiveIssPosition WhereTheIss::fetch() {
    if (auto cached = cache_.get("iss")) return *cached;
    auto res = httpGet("https://api.wheretheiss.at/v1/satellites/25544");
    auto body = nlohmann::json::parse(res.body, nullptr, /*allow_exceptions=*/false);
    if (res.status != 200 || !body.is_object() || !body.contains("latitude")) {
        throw HttpError(res.status, "wheretheiss.at returned HTTP " + std::to_string(res.status));
    }
    LiveIssPosition p{body.value("timestamp", 0.0), body.value("latitude", 0.0), body.value("longitude", 0.0),
                      body.value("altitude", 0.0)};
    cache_.put("iss", p);
    return p;
}
