#pragma once

#include <nlohmann/json.hpp>
#include <string>

#include "http/Cache.hpp"

// Open-Meteo place search: https://open-meteo.com/en/docs/geocoding-api
class Geocoding {
public:
    Geocoding();

    // Up to 8 places matching the name, each {name, region, country, lat, lon}.
    // Throws std::invalid_argument for a query under 2 characters and HttpError on API failure.
    nlohmann::json search(const std::string& query);

private:
    Cache<nlohmann::json> cache_;
};
