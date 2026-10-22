#include "astro/passes.hpp"

#include <algorithm>
#include <cmath>

#include "astro/sun_moon.hpp"

namespace astro {

namespace {

constexpr double kSecond = 1.0 / 86400;
constexpr double kDarkSunAltDeg = -6;
constexpr double kMinVisibleAltDeg = 10;

double altitudeOf(const Sgp4& sat, double jd, const Geodetic& obs) {
    return lookAngles(temeToEcef(sat.at(jd).r, jd), obs).h.altDeg;
}

// Brightness of a diffusely reflecting sphere: the phase angle (Sun-satellite-observer)
// decides how much of the lit side faces us. Normalised to 1 at 90°.
double phaseFactor(double phaseRad) {
    return std::sin(phaseRad) + (kPi - phaseRad) * std::cos(phaseRad);
}

}  // namespace

Geodetic subpoint(const Sgp4& sat, double jd) { return ecefToGeodetic(temeToEcef(sat.at(jd).r, jd)); }

SatelliteView viewSatellite(const Sgp4& sat, double jd, const Geodetic& observer, double stdMagnitude) {
    auto state = sat.at(jd);
    Vec3 ecef = temeToEcef(state.r, jd);
    Vec3 sunTeme = sunDirectionTeme(jd);
    auto look = lookAngles(ecef, observer);

    bool sunlit = !inEarthShadow(state.r, sunTeme);
    Vec3 toObserver = geodeticToEcef(observer) - ecef;
    Vec3 sunEcef = temeToEcef(sunTeme, jd);
    double phase = std::acos(std::clamp(sunEcef.dot(toObserver) / toObserver.norm(), -1.0, 1.0));
    double factor = std::max(phaseFactor(phase), 1e-6);
    double mag = stdMagnitude + 5 * std::log10(look.rangeKm / 1000) - 2.5 * std::log10(factor);

    return {ecefToGeodetic(ecef), look, state.v.norm(), sunlit, mag};
}

std::vector<Pass> findPasses(const Sgp4& sat, const Geodetic& obs, double jd0, double jd1, double stdMagnitude) {
    auto alt = [&](double jd) { return altitudeOf(sat, jd, obs); };
    // Start a little early so a pass already in progress at jd0 has its rise.
    auto xs = findCrossings(alt, jd0 - 20.0 / 1440, jd1, 0, 30 * kSecond);

    std::vector<Pass> passes;
    for (size_t i = 0; i + 1 < xs.size(); ++i) {
        if (!xs[i].rising || xs[i + 1].rising) continue;
        double rise = xs[i].jd, set = xs[i + 1].jd;
        if (set < jd0) continue;

        // The altitude has a single maximum during a pass: golden-section search.
        double a = rise, b = set;
        const double g = (std::sqrt(5.0) - 1) / 2;
        while ((b - a) > kSecond) {
            double c = b - g * (b - a), d = a + g * (b - a);
            if (alt(c) > alt(d)) b = d;
            else a = c;
        }
        double peak = (a + b) / 2;

        Pass p{};
        auto point = [&](double jd) {
            auto h = lookAngles(temeToEcef(sat.at(jd).r, jd), obs).h;
            return PassPoint{jd, h.altDeg, h.azDeg};
        };
        p.rise = point(rise);
        p.peak = point(peak);
        p.set = point(set);
        p.brightestMagnitude = 99;

        // Walk the pass in 10-second steps to find the visible part.
        for (double jd = rise; jd <= set; jd += 10 * kSecond) {
            if (sunHorizontal(jd, obs.latDeg, obs.lonDeg).altDeg > kDarkSunAltDeg) continue;
            auto v = viewSatellite(sat, jd, obs, stdMagnitude);
            if (!v.sunlit || v.look.h.altDeg <= 0) continue;
            PassPoint pt{jd, v.look.h.altDeg, v.look.h.azDeg};
            if (!p.visibleStart) p.visibleStart = pt;
            p.visibleEnd = pt;
            p.visibleMaxAltDeg = std::max(p.visibleMaxAltDeg, pt.altDeg);
            p.brightestMagnitude = std::min(p.brightestMagnitude, v.magnitude);
        }
        p.visible = p.visibleStart && p.visibleMaxAltDeg >= kMinVisibleAltDeg;
        passes.push_back(p);
    }
    return passes;
}

}  // namespace astro
