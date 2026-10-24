"""SGP4 orbit propagator for near-Earth satellites (orbital period under 225
minutes, which covers the ISS and every Starlink satellite).

It follows Vallado, Crawford, Hujsak & Kelso, "Revisiting Spacetrack Report #3"
(2006), with the WGS-72 constants TLEs are generated with. Deep-space orbits
(SDP4) are not supported."""

import math
from typing import NamedTuple

from skywatch.astro.coords import Vec3, rad
from skywatch.astro.tle import Tle

# WGS-72 gravity model, as used to generate TLEs.
_MU = 398600.8  # km^3/s^2
_RE = 6378.135  # Earth radius, km
_XKE = 60.0 / math.sqrt(_RE * _RE * _RE / _MU)  # sqrt(mu) in earth radii^1.5 / min
_J2 = 0.001082616
_J3 = -0.00000253881
_J4 = -0.00000165597
_J3OJ2 = _J3 / _J2
_TWO_PI = 2 * math.pi
_X2O3 = 2.0 / 3.0
_VKMPERSEC = _RE * _XKE / 60


class Sgp4Error(RuntimeError):
    pass


class StateVector(NamedTuple):
    """Position (km) and velocity (km/s) in the TEME frame: Earth-centred, true
    equator, mean equinox of date."""

    r: Vec3
    v: Vec3


class Sgp4:
    # Initialised elements and secular/drag coefficients, named as in Vallado's code.
    __slots__ = (
        "tle", "epoch_jd", "ecco", "inclo", "nodeo", "argpo", "mo", "no", "bstar",
        "ao", "con41", "x1mth2", "x7thm1", "cosio", "sinio", "eta",
        "cc1", "cc4", "cc5", "d2", "d3", "d4", "delmo", "sinmao",
        "mdot", "argpdot", "nodedot", "nodecf", "omgcof", "xmcof", "t2cof", "t3cof", "t4cof", "t5cof",
        "xlcof", "aycof", "isimp",
    )  # fmt: skip

    def __init__(self, tle: Tle):
        """Raises Sgp4Error for deep-space orbits and invalid elements."""
        self.tle = tle
        self.epoch_jd = tle.epoch_jd
        self.ecco = ecco = tle.eccentricity
        self.inclo = inclo = rad(tle.inclination_deg)
        self.nodeo = rad(tle.raan_deg)
        self.argpo = argpo = rad(tle.arg_perigee_deg)
        self.mo = mo = rad(tle.mean_anomaly_deg)
        self.bstar = bstar = tle.bstar
        no_kozai = tle.mean_motion_rev_per_day * _TWO_PI / 1440.0  # rad/min

        # --- initl: recover the original (Brouwer) mean motion and semi-major axis.
        eccsq = ecco * ecco
        omeosq = 1 - eccsq
        rteosq = math.sqrt(omeosq)
        self.cosio = cosio = math.cos(inclo)
        cosio2 = cosio * cosio

        if no_kozai <= 0:
            raise Sgp4Error("invalid orbital elements")
        ak = (_XKE / no_kozai) ** _X2O3
        d1 = 0.75 * _J2 * (3 * cosio2 - 1) / (rteosq * omeosq)
        dl = d1 / (ak * ak)
        adel = ak * (1 - dl * dl - dl * (1.0 / 3.0 + 134 * dl * dl / 81))
        dl = d1 / (adel * adel)
        self.no = no = no_kozai / (1 + dl)

        self.ao = ao = (_XKE / no) ** _X2O3
        self.sinio = sinio = math.sin(inclo)
        po = ao * omeosq
        con42 = 1 - 5 * cosio2
        self.con41 = con41 = -con42 - cosio2 - cosio2
        posq = po * po
        rp = ao * (1 - ecco)

        if _TWO_PI / no >= 225:
            raise Sgp4Error("deep-space orbits (period >= 225 min) are not supported")
        if ecco < 0 or ecco >= 1 or no <= 0:
            raise Sgp4Error("invalid orbital elements")

        # --- sgp4init: secular and drag coefficients.
        # Below 220 km perigee the drag model is simplified (isimp).
        self.isimp = rp < 220 / _RE + 1
        ss = 78 / _RE + 1
        qzms2t = ((120 - 78) / _RE) ** 4
        sfour, qzms24 = ss, qzms2t
        perige = (rp - 1) * _RE
        if perige < 156:
            sfour = 20 if perige < 98 else perige - 78
            qzms24 = ((120 - sfour) / _RE) ** 4
            sfour = sfour / _RE + 1
        pinvsq = 1 / posq
        tsi = 1 / (ao - sfour)
        self.eta = eta = ao * ecco * tsi
        etasq = eta * eta
        eeta = ecco * eta
        psisq = abs(1 - etasq)
        coef = qzms24 * tsi**4
        coef1 = coef / psisq**3.5
        cc2 = (
            coef1
            * no
            * (ao * (1 + 1.5 * etasq + eeta * (4 + etasq)) + 0.375 * _J2 * tsi / psisq * con41 * (8 + 3 * etasq * (8 + etasq)))
        )
        self.cc1 = cc1 = bstar * cc2
        cc3 = -2 * coef * tsi * _J3OJ2 * no * sinio / ecco if ecco > 1e-4 else 0.0
        self.x1mth2 = x1mth2 = 1 - cosio2
        self.cc4 = (
            2
            * no
            * coef1
            * ao
            * omeosq
            * (
                eta * (2 + 0.5 * etasq)
                + ecco * (0.5 + 2 * etasq)
                - _J2
                * tsi
                / (ao * psisq)
                * (
                    -3 * con41 * (1 - 2 * eeta + etasq * (1.5 - 0.5 * eeta))
                    + 0.75 * x1mth2 * (2 * etasq - eeta * (1 + etasq)) * math.cos(2 * argpo)
                )
            )
        )
        self.cc5 = 2 * coef1 * ao * omeosq * (1 + 2.75 * (etasq + eeta) + eeta * etasq)

        cosio4 = cosio2 * cosio2
        temp1 = 1.5 * _J2 * pinvsq * no
        temp2 = 0.5 * temp1 * _J2 * pinvsq
        temp3 = -0.46875 * _J4 * pinvsq * pinvsq * no
        self.mdot = no + 0.5 * temp1 * rteosq * con41 + 0.0625 * temp2 * rteosq * (13 - 78 * cosio2 + 137 * cosio4)
        self.argpdot = (
            -0.5 * temp1 * con42
            + 0.0625 * temp2 * (7 - 114 * cosio2 + 395 * cosio4)
            + temp3 * (3 - 36 * cosio2 + 49 * cosio4)
        )
        xhdot1 = -temp1 * cosio
        self.nodedot = xhdot1 + (0.5 * temp2 * (4 - 19 * cosio2) + 2 * temp3 * (3 - 7 * cosio2)) * cosio
        self.omgcof = bstar * cc3 * math.cos(argpo)
        self.xmcof = -_X2O3 * coef * bstar / eeta if ecco > 1e-4 else 0.0
        self.nodecf = 3.5 * omeosq * xhdot1 * cc1
        self.t2cof = 1.5 * cc1
        # Avoid dividing by zero for an inclination of exactly 180°.
        denom = 1 + cosio if abs(cosio + 1) > 1.5e-12 else 1.5e-12
        self.xlcof = -0.25 * _J3OJ2 * sinio * (3 + 5 * cosio) / denom
        self.aycof = -0.5 * _J3OJ2 * sinio
        self.delmo = (1 + eta * math.cos(mo)) ** 3
        self.sinmao = math.sin(mo)
        self.x7thm1 = 7 * cosio2 - 1

        self.d2 = self.d3 = self.d4 = self.t3cof = self.t4cof = self.t5cof = 0.0
        if not self.isimp:
            cc1sq = cc1 * cc1
            self.d2 = d2 = 4 * ao * tsi * cc1sq
            temp = d2 * tsi * cc1 / 3
            self.d3 = d3 = (17 * ao + sfour) * temp
            self.d4 = d4 = 0.5 * temp * ao * tsi * (221 * ao + 31 * sfour) * cc1
            self.t3cof = d2 + 2 * cc1sq
            self.t4cof = 0.25 * (3 * d3 + cc1 * (12 * d2 + 10 * cc1sq))
            self.t5cof = 0.2 * (3 * d4 + 12 * cc1 * d3 + 6 * d2 * d2 + 15 * cc1sq * (2 * d2 + cc1sq))

    def period_minutes(self) -> float:
        return _TWO_PI / self.no

    def at(self, jd: float) -> StateVector:
        """State at a Julian Date."""
        return self.propagate((jd - self.epoch_jd) * 1440.0)

    def propagate(self, t: float) -> StateVector:
        """State at t minutes after the TLE epoch. Raises Sgp4Error once the
        model breaks down (e.g. the satellite has decayed)."""
        sin, cos, fmod = math.sin, math.cos, math.fmod
        no, ecco, bstar = self.no, self.ecco, self.bstar
        con41, x1mth2, cosio = self.con41, self.x1mth2, self.cosio

        # Secular gravity and atmospheric drag.
        xmdf = self.mo + self.mdot * t
        argpdf = self.argpo + self.argpdot * t
        nodedf = self.nodeo + self.nodedot * t
        argpm = argpdf
        mm = xmdf
        t2 = t * t
        nodem = nodedf + self.nodecf * t2
        tempa = 1 - self.cc1 * t
        tempe = bstar * self.cc4 * t
        templ = self.t2cof * t2

        if not self.isimp:
            delomg = self.omgcof * t
            delm = self.xmcof * ((1 + self.eta * cos(xmdf)) ** 3 - self.delmo)
            temp = delomg + delm
            mm = xmdf + temp
            argpm = argpdf - temp
            t3 = t2 * t
            t4 = t3 * t
            tempa = tempa - self.d2 * t2 - self.d3 * t3 - self.d4 * t4
            tempe = tempe + bstar * self.cc5 * (sin(mm) - self.sinmao)
            templ = templ + self.t3cof * t3 + t4 * (self.t4cof + t * self.t5cof)

        am = (_XKE / no) ** _X2O3 * tempa * tempa
        if am <= 0:
            raise Sgp4Error("semi-major axis < 0: the orbit has decayed")
        nm = _XKE / am**1.5
        em = ecco - tempe
        if em >= 1 or em < -0.001:
            raise Sgp4Error("eccentricity out of range: the orbit has decayed")
        if em < 1e-6:
            em = 1e-6
        mm = mm + no * templ
        xlm = mm + argpm + nodem
        nodem = fmod(nodem, _TWO_PI)
        argpm = fmod(argpm, _TWO_PI)
        xlm = fmod(xlm, _TWO_PI)
        mm = fmod(xlm - argpm - nodem, _TWO_PI)

        # Long-period periodics.
        axnl = em * cos(argpm)
        temp = 1 / (am * (1 - em * em))
        aynl = em * sin(argpm) + temp * self.aycof
        xl = mm + argpm + nodem + temp * self.xlcof * axnl

        # Solve Kepler's equation for (E + ω).
        u = fmod(xl - nodem, _TWO_PI)
        eo1 = u
        sineo1 = coseo1 = 0.0
        tem5 = 9999.9
        ktr = 1
        while abs(tem5) >= 1e-12 and ktr <= 10:
            sineo1 = sin(eo1)
            coseo1 = cos(eo1)
            tem5 = 1 - coseo1 * axnl - sineo1 * aynl
            tem5 = (u - aynl * coseo1 + axnl * sineo1 - eo1) / tem5
            if abs(tem5) >= 0.95:
                tem5 = 0.95 if tem5 > 0 else -0.95
            eo1 += tem5
            ktr += 1

        # Short-period periodics.
        ecose = axnl * coseo1 + aynl * sineo1
        esine = axnl * sineo1 - aynl * coseo1
        el2 = axnl * axnl + aynl * aynl
        pl = am * (1 - el2)
        if pl < 0:
            raise Sgp4Error("semi-latus rectum < 0: the orbit has decayed")
        rl = am * (1 - ecose)
        rdotl = math.sqrt(am) * esine / rl
        rvdotl = math.sqrt(pl) / rl
        betal = math.sqrt(1 - el2)
        temp = esine / (1 + betal)
        sinu = am / rl * (sineo1 - aynl - axnl * temp)
        cosu = am / rl * (coseo1 - axnl + aynl * temp)
        su = math.atan2(sinu, cosu)
        sin2u = (cosu + cosu) * sinu
        cos2u = 1 - 2 * sinu * sinu
        temp = 1 / pl
        temp1 = 0.5 * _J2 * temp
        temp2 = temp1 * temp

        mrt = rl * (1 - 1.5 * temp2 * betal * con41) + 0.5 * temp1 * x1mth2 * cos2u
        su = su - 0.25 * temp2 * self.x7thm1 * sin2u
        xnode = nodem + 1.5 * temp2 * cosio * sin2u
        xinc = self.inclo + 1.5 * temp2 * cosio * self.sinio * cos2u
        mvt = rdotl - nm * temp1 * x1mth2 * sin2u / _XKE
        rvdot = rvdotl + nm * temp1 * (x1mth2 * cos2u + 1.5 * con41) / _XKE

        # Orientation vectors.
        sinsu, cossu = sin(su), cos(su)
        snod, cnod = sin(xnode), cos(xnode)
        sini, cosi = sin(xinc), cos(xinc)
        xmx = -snod * cosi
        xmy = cnod * cosi
        ux, uy, uz = xmx * sinsu + cnod * cossu, xmy * sinsu + snod * cossu, sini * sinsu
        vx, vy, vz = xmx * cossu - cnod * sinsu, xmy * cossu - snod * sinsu, sini * cossu

        if mrt < 1:
            raise Sgp4Error("satellite has decayed")
        k = mrt * _RE
        return StateVector(
            (ux * k, uy * k, uz * k),
            (
                (ux * mvt + vx * rvdot) * _VKMPERSEC,
                (uy * mvt + vy * rvdot) * _VKMPERSEC,
                (uz * mvt + vz * rvdot) * _VKMPERSEC,
            ),
        )
