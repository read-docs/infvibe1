#include "Config.hpp"

#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>

Config Config::load(const std::string& path, const std::string& webRoot) {
    Config cfg;
    cfg.webRoot = webRoot;

    std::ifstream in(path);
    if (!in) {
        std::cerr << "warning: " << path << " not found, using defaults (DEMO_KEY)\n";
        return cfg;
    }

    auto j = nlohmann::json::parse(in);
    cfg.port = j.value("port", cfg.port);
    cfg.nasaApiKey = j.value("nasa_api_key", cfg.nasaApiKey);
    return cfg;
}
