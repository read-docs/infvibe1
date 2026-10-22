#pragma once

#include <cmath>
#include <nlohmann/json.hpp>
#include <optional>

#include "astro/coords.hpp"
#include "astro/time.hpp"

// Small helpers for turning astronomy results into the JSON the frontend reads.

// A Julian Date as whole Unix seconds, or null.
inline nlohmann::json unixOrNull(std::optional<double> jd) {
    return jd ? nlohmann::json(std::llround(astro::unixFromJd(*jd))) : nlohmann::json(nullptr);
}

inline double round1(double x) { return std::round(x * 10) / 10; }

// {alt, az, direction} rounded to 0.1°.
inline nlohmann::json skyPosition(const astro::Horizontal& h) {
    return {{"alt", round1(h.altDeg)}, {"az", round1(h.azDeg)}, {"direction", astro::compassPoint(h.azDeg)}};
}
