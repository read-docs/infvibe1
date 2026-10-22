#include "apis/Swpc.hpp"

#include <ctime>
#include <nlohmann/json.hpp>

#include "http/HttpClient.hpp"

using nlohmann::json;

namespace {

// "2026-10-15T03:00:00" (UTC) -> Unix seconds.
double parseTime(const std::string& s) {
    std::tm tm{};
    if (sscanf(s.c_str(), "%d-%d-%dT%d:%d:%d", &tm.tm_year, &tm.tm_mon, &tm.tm_mday, &tm.tm_hour, &tm.tm_min,
               &tm.tm_sec) < 5) {
        return 0;
    }
    tm.tm_year -= 1900;
    tm.tm_mon -= 1;
    return double(timegm(&tm));
}

double number(const json& v) {
    if (v.is_number()) return v.get<double>();
    if (v.is_string()) return std::stod(v.get<std::string>());
    return -1;
}

json getJson(const std::string& url) {
    auto res = httpGet(url);
    auto body = json::parse(res.body, nullptr, /*allow_exceptions=*/false);
    if (res.status != 200 || !body.is_array()) {
        throw HttpError(res.status, "NOAA SWPC returned HTTP " + std::to_string(res.status));
    }
    return body;
}

}  // namespace

Swpc::Swpc() : cache_(std::chrono::minutes(15)) {}

KpData Swpc::fetch() {
    if (auto cached = cache_.get("kp")) return *cached;

    KpData data;
    for (const auto& row : getJson("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json")) {
        // Current format: objects. Older format: arrays with a header row first.
        if (row.is_object()) {
            data.threeHour.push_back({parseTime(row.value("time_tag", "")), number(row["kp"]), row.value("observed", "")});
        } else if (row.is_array() && row.size() >= 3 && row[1] != "kp") {
            data.threeHour.push_back({parseTime(row[0].get<std::string>()), number(row[1]), row[2].get<std::string>()});
        }
    }
    if (data.threeHour.empty()) throw HttpError(502, "NOAA SWPC returned no Kp data");

    try {
        auto latest = getJson("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json");
        if (!latest.empty()) data.current = latest.back().value("estimated_kp", -1.0);
        if (data.current && *data.current < 0) data.current.reset();
    } catch (const std::exception&) {
        // the 3-hour values are enough
    }
    cache_.put("kp", data);
    return data;
}
