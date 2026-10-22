#include "apis/Celestrak.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <sstream>

#include "astro/tle.hpp"
#include "http/HttpClient.hpp"

namespace {

constexpr double kMaxAgeSeconds = 6 * 3600;
// After every source failed, wait this long before trying again, so a dead
// server doesn't add a timeout to every request.
constexpr double kRetryAfterSeconds = 10 * 60;

double unixNow() {
    using namespace std::chrono;
    return duration<double>(system_clock::now().time_since_epoch()).count();
}

std::shared_ptr<const SatelliteSet> build(const std::string& tleText, double fetched, const std::string& source) {
    auto set = std::make_shared<SatelliteSet>();
    set->fetchedUnix = fetched;
    set->source = source;
    for (const auto& tle : astro::parseTleFile(tleText)) {
        try {
            set->satellites.emplace_back(tle);
        } catch (const astro::Sgp4Error&) {
            // deep-space or broken elements: not something we track
        }
    }
    return set;
}

// SatNOGS JSON ([{tle0, tle1, tle2}, ...]) to TLE text.
std::string satnogsToTle(const std::string& body) {
    auto arr = nlohmann::json::parse(body, nullptr, /*allow_exceptions=*/false);
    std::string out;
    if (!arr.is_array()) return out;
    for (const auto& t : arr) {
        std::string name = t.value("tle0", "");
        if (name.rfind("0 ", 0) == 0) name = name.substr(2);
        out += name + "\n" + t.value("tle1", "") + "\n" + t.value("tle2", "") + "\n";
    }
    return out;
}

}  // namespace

Celestrak::Celestrak(std::string cacheDir) : cacheDir_(std::move(cacheDir)) {
    std::error_code ec;
    std::filesystem::create_directories(cacheDir_, ec);
}

std::shared_ptr<const SatelliteSet> Celestrak::iss() {
    return load("iss", {
        {"CelesTrak", "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE", false},
        {"SatNOGS", "https://db.satnogs.org/api/tle/?norad_cat_id=25544&format=json", true},
    });
}

std::shared_ptr<const SatelliteSet> Celestrak::starlink() {
    return load("starlink", {{"CelesTrak", "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=TLE", false}});
}

Celestrak::Slot& Celestrak::slot(const std::string& key) {
    std::lock_guard<std::mutex> lock(slotsMutex_);
    return slots_[key];  // std::map never moves its elements, so the reference stays valid
}

std::shared_ptr<const SatelliteSet> Celestrak::load(const std::string& key, const std::vector<Source>& sources) {
    Slot& s = slot(key);
    std::lock_guard<std::mutex> lock(s.mutex);
    double now = unixNow();
    auto& current = s.loaded;
    if (current && now - current->fetchedUnix < kMaxAgeSeconds) return current;

    // The disk copy survives restarts. Its first line is "# <fetched unix time> <source>".
    std::string path = cacheDir_ + "/tle-" + key + ".txt";
    if (!current) {
        std::ifstream in(path);
        double fetched = 0;
        std::string hash, source;
        if (in >> hash >> fetched >> source && hash == "#") {
            std::stringstream ss;
            ss << in.rdbuf();
            auto set = build(ss.str(), fetched, source);
            if (!set->satellites.empty()) current = set;
            if (current && now - fetched < kMaxAgeSeconds) return current;
        }
    }

    if (now - s.lastFailure > kRetryAfterSeconds) {
        std::string errors;
        for (const auto& src : sources) {
            try {
                auto res = httpGet(src.url);
                if (res.status != 200) throw HttpError(res.status, "HTTP " + std::to_string(res.status));
                std::string text = src.json ? satnogsToTle(res.body) : res.body;
                auto set = build(text, now, src.name);
                if (set->satellites.empty()) throw HttpError(502, "no usable TLEs in the response");
                std::ofstream(path) << "# " << std::to_string(int64_t(now)) << " " << src.name << "\n" << text;
                current = set;
                return current;
            } catch (const HttpError& e) {
                std::cerr << "warning: " << src.name << " TLE download failed: " << e.what() << "\n";
                errors += (errors.empty() ? "" : "; ") + src.name + ": " + e.what();
            }
        }
        s.lastFailure = now;
        if (!current) throw HttpError(502, "couldn't download satellite orbits (" + errors + ")");
    }
    if (!current) throw HttpError(502, "satellite orbit sources are unreachable; retrying in a few minutes");
    return current;  // stale, but far better than nothing for a few days
}
