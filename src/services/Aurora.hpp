#pragma once

#include <nlohmann/json.hpp>
#include <string>

#include "apis/OpenMeteo.hpp"
#include "apis/Swpc.hpp"

// Geomagnetic latitude in the centred dipole model of Earth's magnetic field
// (pole at 80.8°N, 72.8°W, IGRF 2025). Aurora follows this, not geographic latitude.
double geomagneticLatitude(double latDeg, double lonDeg);

// How likely aurora is for a given Kp at a geomagnetic latitude:
// "overhead", "horizon" (low towards the pole), "camera" (only long exposures
// might catch it) or "none".
std::string auroraChance(double kp, double geomagLatDeg);

// The /api/aurora response: Kp now and forecast, what Kp this location needs,
// and tonight's hours combining the Kp forecast, darkness and clouds.
nlohmann::json auroraReport(const KpData& kp, const Forecast* forecast, double lat, double lon, double nowUnix);
