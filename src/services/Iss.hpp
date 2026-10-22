#pragma once

#include <nlohmann/json.hpp>
#include <optional>

#include "apis/Celestrak.hpp"
#include "apis/OpenMeteo.hpp"
#include "apis/WhereTheIss.hpp"
#include "astro/coords.hpp"

// JSON for the ISS endpoints, all computed with our own SGP4 engine.

// Where the ISS is now; with an observer, also where to look for it.
nlohmann::json issNow(const SatelliteSet& iss, double nowUnix, const std::optional<astro::Geodetic>& observer);

// Our position at the live API's timestamp next to the live one, and the distance between them.
nlohmann::json issCheck(const astro::Sgp4& iss, const LiveIssPosition& live);

// Ground track from minutes before to minutes after now, every 30 seconds.
nlohmann::json issTrack(const astro::Sgp4& iss, double nowUnix, double minutes);

// Passes over the observer in the next `days` days. With a forecast, each
// visible pass also gets the cloud cover and whether the sky is clear enough.
nlohmann::json issPasses(const astro::Sgp4& iss, const astro::Geodetic& observer, double nowUnix, double days,
                         const Forecast* forecast);
