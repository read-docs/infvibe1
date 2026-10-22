#pragma once

#include <nlohmann/json.hpp>

#include "apis/OpenMeteo.hpp"

// How well a body can be seen at one moment: 0 (not at all) to 100 (high in a
// dark, clear sky), and the factor that holds it back most ("too_low",
// "too_bright", "clouds", "moonlight"), or nullptr when nothing does.
// moonGlow is the Moon's illumination while it is up (0 when down); it only
// matters for faint bodies.
struct BodyVisibility {
    int score;
    const char* limit;
};
BodyVisibility bodyVisibility(double altDeg, double magnitude, double sunAltDeg, double cloudBlocking,
                              double moonGlow);

// The /api/planets response: the Moon and the seven planets, where each is now,
// when it next rises and sets, and the stretches of tonight when it is high in
// a dark, mostly clear sky, plus an hourly visibility score from sunset to sunrise
// (the same hours as /api/sky) and the best hour still ahead. Without a forecast
// (weather API down) clouds are ignored.
nlohmann::json planetsReport(double lat, double lon, double nowUnix, const Forecast* forecast);
