#pragma once

#include <nlohmann/json.hpp>

#include "apis/OpenMeteo.hpp"

// Fraction of the sky (0..1) blocked by clouds. Each layer hides what is behind
// it independently; high clouds are mostly thin cirrus, so they count less.
double cloudBlocking(const HourlyWeather& w);

// Cloud blocking above which the sky counts as clouded out, even for bright
// planets or aurora.
constexpr double kMaxCloudBlocking = 0.5;

// Sky condition for a cloud blocking fraction: "clear", "mostly_clear"
// (both good for viewing), "cloudy" or "overcast".
const char* skyCondition(double blocking);

// How good one hour is for stargazing, 0 (nothing to see) to 100 (perfect).
int hourScore(const HourlyWeather& w, double sunAltDeg, double moonAltDeg, double moonIllumination);

// The /api/sky response: Sun and Moon now, tonight's twilight times, and an
// hourly score from sunset to sunrise with the best hour still ahead of nowUnix,
// and a whole-night rating: the average score over the dark hours (Sun below -6°).
nlohmann::json skyReport(const Forecast& forecast, double lat, double lon, double nowUnix);
