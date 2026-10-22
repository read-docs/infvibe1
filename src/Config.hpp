#pragma once

#include <string>

struct Config {
    int port = 8080;
    std::string nasaApiKey = "DEMO_KEY";
    std::string webRoot;

    // Reads config.json; missing file or fields fall back to defaults.
    static Config load(const std::string& path, const std::string& webRoot);
};
