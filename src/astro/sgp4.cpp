#include "astro/sgp4.hpp"

#include <cmath>

#include "astro/coords.hpp"

namespace astro {

namespace {

// WGS-72 gravity model, as used to generate TLEs.
constexpr double kMu = 398600.8;                // km^3/s^2
constexpr double kRe = 6378.135;                // Earth radius, km
const double kXke = 60.0 / std::sqrt(kRe * kRe * kRe / kMu);  // sqrt(mu) in earth radii^1.5 / min
constexpr double kJ2 = 0.001082616;
constexpr double kJ3 = -0.00000253881;
constexpr double kJ4 = -0.00000165597;
constexpr double kJ3oJ2 = kJ3 / kJ2;
constexpr double kTwoPi = 2 * kPi;
constexpr double kX2o3 = 2.0 / 3.0;

}  // namespace

Sgp4::Sgp4(const Tle& tle) : tle_(tle), epochJd_(tle.epochJd) {
    ecco_ = tle.eccentricity;
    inclo_ = rad(tle.inclinationDeg);
    nodeo_ = rad(tle.raanDeg);
    argpo_ = rad(tle.argPerigeeDeg);
    mo_ = rad(tle.meanAnomalyDeg);
    bstar_ = tle.bstar;
    double noKozai = tle.meanMotionRevPerDay * kTwoPi / 1440.0;  // rad/min

    // --- initl: recover the original (Brouwer) mean motion and semi-major axis.
    double eccsq = ecco_ * ecco_;
    double omeosq = 1 - eccsq;
    double rteosq = std::sqrt(omeosq);
    cosio_ = std::cos(inclo_);
    double cosio2 = cosio_ * cosio_;

    double ak = std::pow(kXke / noKozai, kX2o3);
    double d1 = 0.75 * kJ2 * (3 * cosio2 - 1) / (rteosq * omeosq);
    double del = d1 / (ak * ak);
    double adel = ak * (1 - del * del - del * (1.0 / 3.0 + 134 * del * del / 81));
    del = d1 / (adel * adel);
    no_ = noKozai / (1 + del);

    ao_ = std::pow(kXke / no_, kX2o3);
    sinio_ = std::sin(inclo_);
    double po = ao_ * omeosq;
    double con42 = 1 - 5 * cosio2;
    con41_ = -con42 - cosio2 - cosio2;
    double posq = po * po;
    double rp = ao_ * (1 - ecco_);

    if (kTwoPi / no_ >= 225) throw Sgp4Error("deep-space orbits (period >= 225 min) are not supported");
    if (ecco_ < 0 || ecco_ >= 1 || no_ <= 0) throw Sgp4Error("invalid orbital elements");

    // --- sgp4init: secular and drag coefficients.
    // Below 220 km perigee the drag model is simplified (isimp).
    isimp_ = rp < 220 / kRe + 1;
    double ss = 78 / kRe + 1;
    double qzms2t = std::pow((120 - 78) / kRe, 4);
    double sfour = ss, qzms24 = qzms2t;
    double perige = (rp - 1) * kRe;
    if (perige < 156) {
        sfour = perige < 98 ? 20 : perige - 78;
        qzms24 = std::pow((120 - sfour) / kRe, 4);
        sfour = sfour / kRe + 1;
    }
    double pinvsq = 1 / posq;
    double tsi = 1 / (ao_ - sfour);
    eta_ = ao_ * ecco_ * tsi;
    double etasq = eta_ * eta_;
    double eeta = ecco_ * eta_;
    double psisq = std::abs(1 - etasq);
    double coef = qzms24 * std::pow(tsi, 4);
    double coef1 = coef / std::pow(psisq, 3.5);
    double cc2 = coef1 * no_ *
                 (ao_ * (1 + 1.5 * etasq + eeta * (4 + etasq)) +
                  0.375 * kJ2 * tsi / psisq * con41_ * (8 + 3 * etasq * (8 + etasq)));
    cc1_ = bstar_ * cc2;
    double cc3 = ecco_ > 1e-4 ? -2 * coef * tsi * kJ3oJ2 * no_ * sinio_ / ecco_ : 0;
    x1mth2_ = 1 - cosio2;
    cc4_ = 2 * no_ * coef1 * ao_ * omeosq *
           (eta_ * (2 + 0.5 * etasq) + ecco_ * (0.5 + 2 * etasq) -
            kJ2 * tsi / (ao_ * psisq) *
                (-3 * con41_ * (1 - 2 * eeta + etasq * (1.5 - 0.5 * eeta)) +
                 0.75 * x1mth2_ * (2 * etasq - eeta * (1 + etasq)) * std::cos(2 * argpo_)));
    cc5_ = 2 * coef1 * ao_ * omeosq * (1 + 2.75 * (etasq + eeta) + eeta * etasq);

    double cosio4 = cosio2 * cosio2;
    double temp1 = 1.5 * kJ2 * pinvsq * no_;
    double temp2 = 0.5 * temp1 * kJ2 * pinvsq;
    double temp3 = -0.46875 * kJ4 * pinvsq * pinvsq * no_;
    mdot_ = no_ + 0.5 * temp1 * rteosq * con41_ + 0.0625 * temp2 * rteosq * (13 - 78 * cosio2 + 137 * cosio4);
    argpdot_ = -0.5 * temp1 * con42 + 0.0625 * temp2 * (7 - 114 * cosio2 + 395 * cosio4) +
               temp3 * (3 - 36 * cosio2 + 49 * cosio4);
    double xhdot1 = -temp1 * cosio_;
    nodedot_ = xhdot1 + (0.5 * temp2 * (4 - 19 * cosio2) + 2 * temp3 * (3 - 7 * cosio2)) * cosio_;
    omgcof_ = bstar_ * cc3 * std::cos(argpo_);
    xmcof_ = ecco_ > 1e-4 ? -kX2o3 * coef * bstar_ / eeta : 0;
    nodecf_ = 3.5 * omeosq * xhdot1 * cc1_;
    t2cof_ = 1.5 * cc1_;
    // Avoid dividing by zero for an inclination of exactly 180°.
    double denom = std::abs(cosio_ + 1) > 1.5e-12 ? 1 + cosio_ : 1.5e-12;
    xlcof_ = -0.25 * kJ3oJ2 * sinio_ * (3 + 5 * cosio_) / denom;
    aycof_ = -0.5 * kJ3oJ2 * sinio_;
    delmo_ = std::pow(1 + eta_ * std::cos(mo_), 3);
    sinmao_ = std::sin(mo_);
    x7thm1_ = 7 * cosio2 - 1;

    d2_ = d3_ = d4_ = t3cof_ = t4cof_ = t5cof_ = 0;
    if (!isimp_) {
        double cc1sq = cc1_ * cc1_;
        d2_ = 4 * ao_ * tsi * cc1sq;
        double temp = d2_ * tsi * cc1_ / 3;
        d3_ = (17 * ao_ + sfour) * temp;
        d4_ = 0.5 * temp * ao_ * tsi * (221 * ao_ + 31 * sfour) * cc1_;
        t3cof_ = d2_ + 2 * cc1sq;
        t4cof_ = 0.25 * (3 * d3_ + cc1_ * (12 * d2_ + 10 * cc1sq));
        t5cof_ = 0.2 * (3 * d4_ + 12 * cc1_ * d3_ + 6 * d2_ * d2_ + 15 * cc1sq * (2 * d2_ + cc1sq));
    }
}

double Sgp4::periodMinutes() const { return kTwoPi / no_; }

StateVector Sgp4::propagate(double t) const {
    // Secular gravity and atmospheric drag.
    double xmdf = mo_ + mdot_ * t;
    double argpdf = argpo_ + argpdot_ * t;
    double nodedf = nodeo_ + nodedot_ * t;
    double argpm = argpdf;
    double mm = xmdf;
    double t2 = t * t;
    double nodem = nodedf + nodecf_ * t2;
    double tempa = 1 - cc1_ * t;
    double tempe = bstar_ * cc4_ * t;
    double templ = t2cof_ * t2;

    if (!isimp_) {
        double delomg = omgcof_ * t;
        double delm = xmcof_ * (std::pow(1 + eta_ * std::cos(xmdf), 3) - delmo_);
        double temp = delomg + delm;
        mm = xmdf + temp;
        argpm = argpdf - temp;
        double t3 = t2 * t, t4 = t3 * t;
        tempa = tempa - d2_ * t2 - d3_ * t3 - d4_ * t4;
        tempe = tempe + bstar_ * cc5_ * (std::sin(mm) - sinmao_);
        templ = templ + t3cof_ * t3 + t4 * (t4cof_ + t * t5cof_);
    }

    double am = std::pow(kXke / no_, kX2o3) * tempa * tempa;
    double nm = kXke / std::pow(am, 1.5);
    double em = ecco_ - tempe;
    if (em >= 1 || em < -0.001) throw Sgp4Error("eccentricity out of range: the orbit has decayed");
    if (em < 1e-6) em = 1e-6;
    mm = mm + no_ * templ;
    double xlm = mm + argpm + nodem;
    nodem = std::fmod(nodem, kTwoPi);
    argpm = std::fmod(argpm, kTwoPi);
    xlm = std::fmod(xlm, kTwoPi);
    mm = std::fmod(xlm - argpm - nodem, kTwoPi);

    // Long-period periodics.
    double axnl = em * std::cos(argpm);
    double temp = 1 / (am * (1 - em * em));
    double aynl = em * std::sin(argpm) + temp * aycof_;
    double xl = mm + argpm + nodem + temp * xlcof_ * axnl;

    // Solve Kepler's equation for (E + ω).
    double u = std::fmod(xl - nodem, kTwoPi);
    double eo1 = u, sineo1 = 0, coseo1 = 0;
    double tem5 = 9999.9;
    for (int ktr = 1; std::abs(tem5) >= 1e-12 && ktr <= 10; ++ktr) {
        sineo1 = std::sin(eo1);
        coseo1 = std::cos(eo1);
        tem5 = 1 - coseo1 * axnl - sineo1 * aynl;
        tem5 = (u - aynl * coseo1 + axnl * sineo1 - eo1) / tem5;
        if (std::abs(tem5) >= 0.95) tem5 = tem5 > 0 ? 0.95 : -0.95;
        eo1 += tem5;
    }

    // Short-period periodics.
    double ecose = axnl * coseo1 + aynl * sineo1;
    double esine = axnl * sineo1 - aynl * coseo1;
    double el2 = axnl * axnl + aynl * aynl;
    double pl = am * (1 - el2);
    if (pl < 0) throw Sgp4Error("semi-latus rectum < 0: the orbit has decayed");
    double rl = am * (1 - ecose);
    double rdotl = std::sqrt(am) * esine / rl;
    double rvdotl = std::sqrt(pl) / rl;
    double betal = std::sqrt(1 - el2);
    temp = esine / (1 + betal);
    double sinu = am / rl * (sineo1 - aynl - axnl * temp);
    double cosu = am / rl * (coseo1 - axnl + aynl * temp);
    double su = std::atan2(sinu, cosu);
    double sin2u = (cosu + cosu) * sinu;
    double cos2u = 1 - 2 * sinu * sinu;
    temp = 1 / pl;
    double temp1 = 0.5 * kJ2 * temp;
    double temp2 = temp1 * temp;

    double mrt = rl * (1 - 1.5 * temp2 * betal * con41_) + 0.5 * temp1 * x1mth2_ * cos2u;
    su = su - 0.25 * temp2 * x7thm1_ * sin2u;
    double xnode = nodem + 1.5 * temp2 * cosio_ * sin2u;
    double xinc = inclo_ + 1.5 * temp2 * cosio_ * sinio_ * cos2u;
    double mvt = rdotl - nm * temp1 * x1mth2_ * sin2u / kXke;
    double rvdot = rvdotl + nm * temp1 * (x1mth2_ * cos2u + 1.5 * con41_) / kXke;

    // Orientation vectors.
    double sinsu = std::sin(su), cossu = std::cos(su);
    double snod = std::sin(xnode), cnod = std::cos(xnode);
    double sini = std::sin(xinc), cosi = std::cos(xinc);
    double xmx = -snod * cosi, xmy = cnod * cosi;
    Vec3 uv{xmx * sinsu + cnod * cossu, xmy * sinsu + snod * cossu, sini * sinsu};
    Vec3 vv{xmx * cossu - cnod * sinsu, xmy * cossu - snod * sinsu, sini * cossu};

    if (mrt < 1) throw Sgp4Error("satellite has decayed");
    double vkmpersec = kRe * kXke / 60;
    return {uv * (mrt * kRe), (uv * mvt + vv * rvdot) * vkmpersec};
}

}  // namespace astro
