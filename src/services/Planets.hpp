#pragma once

#include <nlohmann/json.hpp>

#include "apis/OpenMeteo.hpp"

// The /api/planets response: the Moon and the seven planets, where each is now,
// when it next rises and sets, and the stretches of tonight when it is high in
// a dark, mostly clear sky. Without a forecast (weather API down) clouds are ignored.
nlohmann::json planetsReport(double lat, double lon, double nowUnix, const Forecast* forecast);
