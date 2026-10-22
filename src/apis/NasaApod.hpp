#pragma once

#include <nlohmann/json.hpp>
#include <string>

#include "http/Cache.hpp"

// NASA Astronomy Picture of the Day: https://api.nasa.gov/
class NasaApod {
public:
    explicit NasaApod(std::string apiKey);

    // date is "YYYY-MM-DD", or empty for today. Returns the APOD fields the
    // frontend uses. Throws std::invalid_argument for a malformed date and
    // HttpError when NASA rejects the request.
    nlohmann::json fetch(const std::string& date);

private:
    nlohmann::json request(const std::string& date);

    std::string apiKey_;
    Cache<nlohmann::json> pastCache_;
    Cache<nlohmann::json> todayCache_;
};
