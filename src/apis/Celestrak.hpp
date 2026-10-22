#pragma once

#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "astro/sgp4.hpp"

struct SatelliteSet {
    std::vector<astro::Sgp4> satellites;
    double fetchedUnix;  // when the TLEs were downloaded
    std::string source;  // where they came from
};

// Satellite orbits (TLEs) from CelesTrak: https://celestrak.org/NORAD/documentation/gp-data-formats.php
// CelesTrak blocks clients that download the same data more than once every
// 2 hours, so every set is cached in memory and on disk for 6 hours, and after
// a failed download the last good copy is used. The ISS also has a fallback
// source (SatNOGS, which mirrors Space-Track) for when CelesTrak is unreachable.
class Celestrak {
public:
    explicit Celestrak(std::string cacheDir);

    // Throw HttpError when no source works and nothing is cached.
    std::shared_ptr<const SatelliteSet> iss();
    std::shared_ptr<const SatelliteSet> starlink();

private:
    struct Source {
        std::string name;
        std::string url;
        bool json;  // SatNOGS returns JSON instead of TLE text
    };
    std::shared_ptr<const SatelliteSet> load(const std::string& key, const std::vector<Source>& sources);

    // Per set (ISS, Starlink): a slow Starlink download must not stall ISS
    // requests. Concurrent requests for the same set wait for one download.
    struct Slot {
        std::mutex mutex;
        std::shared_ptr<const SatelliteSet> loaded;
        double lastFailure = 0;
    };
    Slot& slot(const std::string& key);

    std::string cacheDir_;
    std::mutex slotsMutex_;  // guards slots_ itself
    std::map<std::string, Slot> slots_;
};
