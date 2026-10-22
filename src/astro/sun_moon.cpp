#include "astro/sun_moon.hpp"

#include <algorithm>

#include "astro/time.hpp"

namespace astro {

namespace {

constexpr double kEarthRadiusKm = 6378.14;
constexpr double kAuKm = 149597870.7;

// Longitude of the Moon's ascending node, used for the nutation corrections.
double nodeDeg(double t) { return 125.04 - 1934.136 * t; }

struct SunTerms {
    double trueLonDeg;
    double anomalyDeg;  // true anomaly
    double ecc;
};

SunTerms sunTerms(double t) {
    double l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t;
    double m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t;
    double c = (1.914602 - 0.004817 * t - 0.000014 * t * t) * sinDeg(m) +
               (0.019993 - 0.000101 * t) * sinDeg(2 * m) + 0.000289 * sinDeg(3 * m);
    double ecc = 0.016708634 - 0.000042037 * t - 0.0000001267 * t * t;
    return {normDeg(l0 + c), m + c, ecc};
}

// Obliquity including the main nutation term, for apparent positions.
double apparentObliquityDeg(double jd) {
    return obliquityDeg(jd) + 0.00256 * cosDeg(nodeDeg(centuriesSinceJ2000(jd)));
}

// Periodic terms for the Moon's longitude and distance (Meeus table 47.A),
// truncated to coefficients above 0.002°: multiples of D, M, M', F, then
// Σl in 1e-6 degrees and Σr in 1e-3 km.
struct LonDistTerm {
    int d, m, mp, f;
    double l, r;
};
constexpr LonDistTerm kMoonLonDist[] = {
    {0, 0, 1, 0, 6288774, -20905355}, {2, 0, -1, 0, 1274027, -3699111},
    {2, 0, 0, 0, 658314, -2955968},   {0, 0, 2, 0, 213618, -569925},
    {0, 1, 0, 0, -185116, 48888},     {0, 0, 0, 2, -114332, -3149},
    {2, 0, -2, 0, 58793, 246158},     {2, -1, -1, 0, 57066, -152138},
    {2, 0, 1, 0, 53322, -170733},     {2, -1, 0, 0, 45758, -204586},
    {0, 1, -1, 0, -40923, -129620},   {1, 0, 0, 0, -34720, 108743},
    {0, 1, 1, 0, -30383, 104755},     {2, 0, 0, -2, 15327, 10321},
    {0, 0, 1, 2, -12528, 0},          {0, 0, 1, -2, 10980, 79661},
    {4, 0, -1, 0, 10675, -34782},     {0, 0, 3, 0, 10034, -23210},
    {4, 0, -2, 0, 8548, -21636},      {2, 1, -1, 0, -7888, 24208},
    {2, 1, 0, 0, -6766, 30824},       {1, 0, -1, 0, -5163, -8379},
    {1, 1, 0, 0, 4987, -16675},       {2, -1, 1, 0, 4036, -12831},
    {2, 0, 2, 0, 3994, -10445},       {4, 0, 0, 0, 3861, -11650},
    {2, 0, -3, 0, 3665, 14403},       {0, 1, -2, 0, -2689, -7003},
    {2, 0, -1, 2, -2602, 0},          {2, -1, -2, 0, 2390, 10056},
    {1, 0, 1, 0, -2348, 6322},        {2, -2, 0, 0, 2236, -9884},
};

// Periodic terms for the Moon's latitude (Meeus table 47.B), truncated the same way.
struct LatTerm {
    int d, m, mp, f;
    double b;
};
constexpr LatTerm kMoonLat[] = {
    {0, 0, 0, 1, 5128122}, {0, 0, 1, 1, 280602}, {0, 0, 1, -1, 277693}, {2, 0, 0, -1, 173237},
    {2, 0, -1, 1, 55413},  {2, 0, -1, -1, 46271}, {2, 0, 0, 1, 32573},  {0, 0, 2, 1, 17198},
    {2, 0, 1, -1, 9266},   {0, 0, 2, -1, 8822},  {2, -1, 0, -1, 8216},  {2, 0, -2, -1, 4324},
    {2, 0, 1, 1, 4200},    {2, 1, 0, -1, -3359}, {2, -1, -1, 1, 2463},  {2, -1, 0, 1, 2211},
    {2, -1, -1, -1, 2065},
};

}  // namespace

Ecliptic sunEcliptic(double jd) {
    double t = centuriesSinceJ2000(jd);
    // Aberration (-0.00569°) and nutation in longitude turn the true longitude into the apparent one.
    double lon = sunTerms(t).trueLonDeg - 0.00569 - 0.00478 * sinDeg(nodeDeg(t));
    return {normDeg(lon), 0.0};
}

double sunDistanceKm(double jd) {
    auto s = sunTerms(centuriesSinceJ2000(jd));
    double au = 1.000001018 * (1 - s.ecc * s.ecc) / (1 + s.ecc * cosDeg(s.anomalyDeg));
    return au * kAuKm;
}

Equatorial sunEquatorial(double jd) {
    return eclipticToEquatorial(sunEcliptic(jd), apparentObliquityDeg(jd));
}

MoonPosition moonPosition(double jd) {
    double t = centuriesSinceJ2000(jd);
    double t2 = t * t, t3 = t2 * t, t4 = t3 * t;
    double lp = normDeg(218.3164477 + 481267.88123421 * t - 0.0015786 * t2 + t3 / 538841 - t4 / 65194000);
    double d = normDeg(297.8501921 + 445267.1114034 * t - 0.0018819 * t2 + t3 / 545868 - t4 / 113065000);
    double m = normDeg(357.5291092 + 35999.0502909 * t - 0.0001536 * t2 + t3 / 24490000);
    double mp = normDeg(134.9633964 + 477198.8675055 * t + 0.0087414 * t2 + t3 / 69699 - t4 / 14712000);
    double f = normDeg(93.2720950 + 483202.0175233 * t - 0.0036539 * t2 - t3 / 3526000 + t4 / 863310000);
    double a1 = 119.75 + 131.849 * t;
    double a2 = 53.09 + 479264.290 * t;
    double a3 = 313.45 + 481266.484 * t;
    // Terms involving the Sun's anomaly M shrink as Earth's orbit becomes less eccentric.
    double e = 1 - 0.002516 * t - 0.0000074 * t2;
    auto eFactor = [e](int mult) { return mult == 0 ? 1.0 : (mult == 1 || mult == -1) ? e : e * e; };

    double sumL = 0, sumR = 0, sumB = 0;
    for (const auto& k : kMoonLonDist) {
        double arg = k.d * d + k.m * m + k.mp * mp + k.f * f;
        double ef = eFactor(k.m);
        sumL += k.l * ef * sinDeg(arg);
        sumR += k.r * ef * cosDeg(arg);
    }
    for (const auto& k : kMoonLat) {
        sumB += k.b * eFactor(k.m) * sinDeg(k.d * d + k.m * m + k.mp * mp + k.f * f);
    }
    // Perturbations by Venus (A1), Jupiter (A2) and Earth's flattening (L' terms).
    sumL += 3958 * sinDeg(a1) + 1962 * sinDeg(lp - f) + 318 * sinDeg(a2);
    sumB += -2235 * sinDeg(lp) + 382 * sinDeg(a3) + 175 * sinDeg(a1 - f) + 175 * sinDeg(a1 + f) +
            127 * sinDeg(lp - mp) - 115 * sinDeg(lp + mp);

    double nutationLon = -0.00478 * sinDeg(nodeDeg(t));
    Ecliptic ecl{normDeg(lp + sumL / 1e6 + nutationLon), sumB / 1e6};
    return {ecl, eclipticToEquatorial(ecl, apparentObliquityDeg(jd)), 385000.56 + sumR / 1000};
}

Horizontal sunHorizontal(double jd, double latDeg, double lonDeg) {
    return equatorialToHorizontal(sunEquatorial(jd), lmstDeg(jd, lonDeg), latDeg);
}

Horizontal moonHorizontal(double jd, double latDeg, double lonDeg) {
    auto moon = moonPosition(jd);
    auto h = equatorialToHorizontal(moon.eq, lmstDeg(jd, lonDeg), latDeg);
    // Seen from the surface rather than Earth's centre, the Moon sits lower by
    // its horizontal parallax times cos(altitude).
    double parallax = deg(std::asin(kEarthRadiusKm / moon.distanceKm));
    h.altDeg -= parallax * cosDeg(h.altDeg);
    return h;
}

MoonPhase moonPhase(double jd) {
    auto moon = moonPosition(jd);
    auto sun = sunEcliptic(jd);
    double sunKm = sunDistanceKm(jd);

    // Geocentric elongation ψ, then the phase angle i seen from the Moon (Meeus 48.2, 48.3).
    double cosPsi = cosDeg(moon.ecl.latDeg) * cosDeg(moon.ecl.lonDeg - sun.lonDeg);
    double psi = std::acos(cosPsi);
    double i = std::atan2(sunKm * std::sin(psi), moon.distanceKm - sunKm * cosPsi);
    double illum = (1 + std::cos(i)) / 2;

    double age = normDeg(moon.ecl.lonDeg - sun.lonDeg);
    bool waxing = age < 180;
    const char* name;
    // The four principal phases each get a ±7° (about half a day) window.
    if (age < 7 || age >= 353) name = "New Moon";
    else if (age < 83) name = "Waxing Crescent";
    else if (age < 97) name = "First Quarter";
    else if (age < 173) name = "Waxing Gibbous";
    else if (age < 187) name = "Full Moon";
    else if (age < 263) name = "Waning Gibbous";
    else if (age < 277) name = "Last Quarter";
    else name = "Waning Crescent";
    return {illum, age, waxing, name};
}

std::vector<Crossing> findCrossings(const std::function<double(double)>& altitudeDeg, double jd0,
                                    double jd1, double thresholdDeg, double stepDays) {
    std::vector<Crossing> out;
    double prevT = jd0;
    double prevV = altitudeDeg(jd0) - thresholdDeg;
    while (prevT < jd1) {
        double t = std::min(prevT + stepDays, jd1);
        double v = altitudeDeg(t) - thresholdDeg;
        if ((prevV < 0) != (v < 0)) {
            double lo = prevT, hi = t, loV = prevV;
            while ((hi - lo) * 86400 > 1) {
                double mid = (lo + hi) / 2;
                double midV = altitudeDeg(mid) - thresholdDeg;
                if ((midV < 0) == (loV < 0)) {
                    lo = mid;
                    loV = midV;
                } else {
                    hi = mid;
                }
            }
            out.push_back({(lo + hi) / 2, prevV < 0});
        }
        prevT = t;
        prevV = v;
    }
    return out;
}

std::optional<double> firstCrossingAfter(const std::vector<Crossing>& xs, double jd, bool rising) {
    for (const auto& x : xs) {
        if (x.jd > jd && x.rising == rising) return x.jd;
    }
    return std::nullopt;
}

std::optional<double> lastCrossingBefore(const std::vector<Crossing>& xs, double jd, bool rising) {
    std::optional<double> found;
    for (const auto& x : xs) {
        if (x.jd <= jd && x.rising == rising) found = x.jd;
    }
    return found;
}

Night tonight(double jdNow, double latDeg, double lonDeg) {
    auto sunAlt = [&](double jd) { return sunHorizontal(jd, latDeg, lonDeg).altDeg; };
    auto xs = findCrossings(sunAlt, jdNow - 1, jdNow + 2, kRiseSetAltDeg);
    std::optional<double> sunset, sunrise;
    if (sunAlt(jdNow) < kRiseSetAltDeg) {
        sunset = lastCrossingBefore(xs, jdNow, false);
        sunrise = firstCrossingAfter(xs, jdNow, true);
        if (!sunset || !sunrise) return {jdNow, jdNow + 1, "night"};
    } else {
        sunset = firstCrossingAfter(xs, jdNow, false);
        if (!sunset) return {jdNow, jdNow + 1, "day"};
        sunrise = firstCrossingAfter(xs, *sunset, true);
        if (!sunrise) return {jdNow, jdNow + 1, "night"};
    }
    return {*sunset, *sunrise, nullptr};
}

}  // namespace astro
