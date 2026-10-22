#pragma once

#include <nlohmann/json.hpp>

#include "apis/Celestrak.hpp"
#include "apis/OpenMeteo.hpp"

// The /api/starlink response: how many Starlink satellites are above the
// observer right now, how many of them can actually be seen (sunlit in a dark
// sky), the most recent launches, and the position of each one above the horizon.
// With a forecast, an overcast sky means none of them count as visible.
nlohmann::json starlinkReport(const SatelliteSet& set, double lat, double lon, double nowUnix,
                              const Forecast* forecast = nullptr);
