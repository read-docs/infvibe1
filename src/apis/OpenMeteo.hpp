#pragma once

#include <string>
#include <vector>

#include "http/Cache.hpp"

struct HourlyWeather {
    double time;              // Unix seconds, start of the hour
    double cloudCover;        // total, %
    double cloudLow;          // %, below ~2 km
    double cloudMid;          // %, 2-6 km
    double cloudHigh;         // %, above 6 km
    double visibilityM;
    double humidity;          // relative, %
    double precipProbability; // %
};

struct Forecast {
    std::string timezone;  // IANA name, e.g. "Europe/Warsaw"
    int utcOffsetSeconds;
    std::vector<HourlyWeather> hours;
};

// The forecast hour containing unixTime, or nullptr if it is outside the forecast.
const HourlyWeather* weatherAt(const Forecast& f, double unixTime);

// Open-Meteo hourly forecast: https://open-meteo.com/en/docs
class OpenMeteo {
public:
    OpenMeteo();

    // Four days of hourly data starting at local midnight today (enough for
    // 3-day ISS pass predictions).
    // Throws HttpError when the API is unreachable or rejects the request.
    Forecast forecast(double lat, double lon);

private:
    Cache<Forecast> cache_;
};
