#pragma once

#include <optional>
#include <string>
#include <vector>

#include "http/Cache.hpp"

// NOAA Space Weather Prediction Center: the planetary K index (Kp, 0-9), a
// measure of geomagnetic activity. https://www.swpc.noaa.gov/products/planetary-k-index
struct KpPoint {
    double time;       // Unix seconds, start of the 3-hour interval
    double kp;
    std::string kind;  // "observed", "estimated" or "predicted"
};

struct KpData {
    std::vector<KpPoint> threeHour;  // last week observed + next 3 days predicted
    std::optional<double> current;   // latest 1-minute estimate
};

class Swpc {
public:
    Swpc();
    // Throws HttpError if the 3-hour data can't be fetched; the 1-minute
    // estimate is optional.
    KpData fetch();

private:
    Cache<KpData> cache_;
};
