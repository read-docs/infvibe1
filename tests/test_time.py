from helpers import approx

from skywatch.astro.coords import Equatorial, compass_point, equatorial_to_horizontal
from skywatch.astro.time import J2000, gmst_deg, jd_from_unix, unix_from_jd


def test_julian_date_from_unix_time():
    assert jd_from_unix(0) == approx(2440587.5)
    assert jd_from_unix(946728000) == approx(J2000)  # 2000-01-01 12:00 UTC
    assert unix_from_jd(jd_from_unix(1761134400)) == approx(1761134400)


def test_greenwich_mean_sidereal_time():
    # Meeus examples 12.a and 12.b
    assert gmst_deg(2446895.5) == approx(197.693195, 1e-8)
    assert gmst_deg(2446896.30625) == approx(128.7378734, 1e-8)


def test_equatorial_to_horizontal():
    # Meeus example 13.b, Venus from Washington, 1987-04-10 19:21 UT; apparent
    # sidereal time 8h34m56.853s, observer 38°55'17"N 77°03'56"W.
    venus = Equatorial(347.3193375, -6.719892)
    h = equatorial_to_horizontal(venus, 128.736888 - 77.065556, 38.921389)
    assert h.alt_deg == approx(15.1249, 1e-4)
    # Meeus measures azimuth from the south: 68.0337° there is 248.0337° from north.
    assert h.az_deg == approx(248.0337, 1e-4)


def test_compass_points():
    assert compass_point(0) == "N"
    assert compass_point(359) == "N"
    assert compass_point(90) == "E"
    assert compass_point(135) == "SE"
    assert compass_point(260) == "W"
