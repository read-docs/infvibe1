#pragma once

#include <optional>

#include "http/Cache.hpp"

// The ISS position published by https://wheretheiss.at, used only to check our
// own SGP4 engine against an independent source.
struct LiveIssPosition {
    double unixTime;
    double latDeg;
    double lonDeg;
    double altKm;
};

class WhereTheIss {
public:
    WhereTheIss();
    // Throws HttpError on failure. Cached for a few seconds: the API allows ~1 request/s.
    LiveIssPosition fetch();

private:
    Cache<LiveIssPosition> cache_;
};
