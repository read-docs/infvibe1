#include <httplib.h>

#include <chrono>
#include <cmath>
#include <iostream>
#include <optional>
#include <nlohmann/json.hpp>

#include "Config.hpp"
#include "apis/Celestrak.hpp"
#include "apis/Geocoding.hpp"
#include "apis/NasaApod.hpp"
#include "apis/OpenMeteo.hpp"
#include "apis/Swpc.hpp"
#include "apis/WhereTheIss.hpp"
#include "http/HttpClient.hpp"
#include "services/Aurora.hpp"
#include "services/Iss.hpp"
#include "services/Planets.hpp"
#include "services/SkyQuality.hpp"
#include "services/Starlink.hpp"

using nlohmann::json;

namespace {

void sendJson(httplib::Response& res, const json& body, int status = 200) {
    res.status = status;
    res.set_content(body.dump(), "application/json");
}

void sendError(httplib::Response& res, int status, const std::string& message) {
    sendJson(res, {{"error", message}}, status);
}

// Parses a required numeric query parameter within [min, max]; throws std::invalid_argument.
double numberParam(const httplib::Request& req, const std::string& name, double min, double max) {
    std::string raw = req.get_param_value(name);
    size_t used = 0;
    double value = NAN;
    try {
        value = std::stod(raw, &used);
    } catch (const std::exception&) {
    }
    if (raw.empty() || used != raw.size() || !(value >= min && value <= max)) {
        throw std::invalid_argument(name + " must be a number between " + std::to_string(int(min)) +
                                    " and " + std::to_string(int(max)));
    }
    return value;
}

// Runs a handler, turning bad input into 400 and upstream API failures into 502.
template <typename Handler>
void handle(httplib::Response& res, Handler handler) {
    try {
        sendJson(res, handler());
    } catch (const std::invalid_argument& e) {
        sendError(res, 400, e.what());
    } catch (const HttpError& e) {
        sendError(res, 502, e.what());
    }
}

// Optional observer from ?lat=&lon=; both or neither must be given.
std::optional<astro::Geodetic> optionalObserver(const httplib::Request& req) {
    if (!req.has_param("lat") && !req.has_param("lon")) return std::nullopt;
    return astro::Geodetic{numberParam(req, "lat", -90, 90), numberParam(req, "lon", -180, 180), 0};
}

// Planets and aurora are still worth showing when the weather API is down, just without clouds.
std::optional<Forecast> optionalForecast(OpenMeteo& weather, double lat, double lon) {
    try {
        return weather.forecast(lat, lon);
    } catch (const HttpError& e) {
        std::cerr << "warning: no forecast, ignoring clouds: " << e.what() << "\n";
        return std::nullopt;
    }
}

double unixNow() {
    using namespace std::chrono;
    return duration<double>(system_clock::now().time_since_epoch()).count();
}

}  // namespace

int main() {
    const std::string root = SKYWATCH_ROOT;
    Config cfg = Config::load(root + "/config.json", root + "/web");

    NasaApod apod(cfg.nasaApiKey);
    OpenMeteo weather;
    Geocoding geocoding;
    Celestrak celestrak(root + "/cache");
    WhereTheIss whereTheIss;
    Swpc swpc;

    httplib::Server server;

    server.Get("/api/health", [](const httplib::Request&, httplib::Response& res) {
        sendJson(res, {{"status", "ok"}});
    });

    server.Get("/api/apod", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            sendJson(res, apod.fetch(req.get_param_value("date")));
        } catch (const std::invalid_argument& e) {
            sendError(res, 400, e.what());
        } catch (const HttpError& e) {
            // A 4xx from NASA (e.g. date out of range) is the client's fault; anything else is upstream.
            sendError(res, e.status >= 400 && e.status < 500 ? 400 : 502, e.what());
        }
    });

    server.Get("/api/geocode", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] { return geocoding.search(req.get_param_value("q")); });
    });

    server.Get("/api/sky", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] {
            double lat = numberParam(req, "lat", -90, 90);
            double lon = numberParam(req, "lon", -180, 180);
            return skyReport(weather.forecast(lat, lon), lat, lon, unixNow());
        });
    });

    server.Get("/api/planets", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] {
            double lat = numberParam(req, "lat", -90, 90);
            double lon = numberParam(req, "lon", -180, 180);
            auto forecast = optionalForecast(weather, lat, lon);
            return planetsReport(lat, lon, unixNow(), forecast ? &*forecast : nullptr);
        });
    });

    server.Get("/api/iss/now", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] {
            auto observer = optionalObserver(req);
            auto iss = celestrak.iss();
            json out = issNow(*iss, unixNow(), observer);
            // The comparison is optional: the live API being down shouldn't hide our own result.
            if (req.get_param_value("check") == "1") {
                try {
                    out["check"] = issCheck(iss->satellites.front(), whereTheIss.fetch());
                } catch (const HttpError& e) {
                    out["check"] = {{"error", e.what()}};
                }
            }
            return out;
        });
    });

    server.Get("/api/iss/track", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] {
            double minutes = req.has_param("minutes") ? numberParam(req, "minutes", 1, 300) : 95;
            return issTrack(celestrak.iss()->satellites.front(), unixNow(), minutes);
        });
    });

    server.Get("/api/iss/passes", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] {
            astro::Geodetic observer{numberParam(req, "lat", -90, 90), numberParam(req, "lon", -180, 180), 0};
            double days = req.has_param("days") ? numberParam(req, "days", 1, 10) : 3;
            auto forecast = optionalForecast(weather, observer.latDeg, observer.lonDeg);
            return issPasses(celestrak.iss()->satellites.front(), observer, unixNow(), days,
                             forecast ? &*forecast : nullptr);
        });
    });

    server.Get("/api/starlink", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] {
            double lat = numberParam(req, "lat", -90, 90);
            double lon = numberParam(req, "lon", -180, 180);
            auto starlink = celestrak.starlink();  // first: no point fetching weather if this fails
            auto forecast = optionalForecast(weather, lat, lon);
            return starlinkReport(*starlink, lat, lon, unixNow(), forecast ? &*forecast : nullptr);
        });
    });

    server.Get("/api/aurora", [&](const httplib::Request& req, httplib::Response& res) {
        handle(res, [&] {
            double lat = numberParam(req, "lat", -90, 90);
            double lon = numberParam(req, "lon", -180, 180);
            auto forecast = optionalForecast(weather, lat, lon);
            return auroraReport(swpc.fetch(), forecast ? &*forecast : nullptr, lat, lon, unixNow());
        });
    });

    if (!server.set_mount_point("/", cfg.webRoot)) {
        std::cerr << "error: web directory not found: " << cfg.webRoot << "\n";
        return 1;
    }

    if (!server.bind_to_port("127.0.0.1", cfg.port)) {
        std::cerr << "error: could not listen on port " << cfg.port << "\n";
        return 1;
    }
    std::cout << "SkyWatch running at http://localhost:" << cfg.port << std::endl;
    server.listen_after_bind();
}
