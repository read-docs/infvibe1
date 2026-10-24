import math

from helpers import approx

from skywatch.astro.sun_moon import find_crossings, moon_phase, moon_position, sun_distance_km, sun_ecliptic, sun_equatorial


def test_sun_position():
    # Meeus example 25.a, 1992-10-13 0h
    jd = 2448908.5
    assert sun_ecliptic(jd).lon_deg == approx(199.90895, 1e-6)
    eq = sun_equatorial(jd)
    assert eq.ra_deg == approx(198.38083, 1e-6)
    assert eq.dec_deg == approx(-7.78507, 1e-5)
    assert sun_distance_km(jd) / 149597870.7 == approx(0.99766, 1e-5)


def test_moon_position():
    # Meeus example 47.a, 1992-04-12 0h. The tables are truncated, so allow
    # ~0.01° instead of Meeus's full precision.
    moon = moon_position(2448724.5)
    assert moon.ecl.lon_deg == approx(133.162655, 1e-4)
    assert moon.ecl.lat_deg == approx(-3.229126, 3e-3)
    assert moon.distance_km == approx(368409.7, 1e-4)
    assert moon.eq.ra_deg == approx(134.688470, 1e-4)
    assert moon.eq.dec_deg == approx(13.768368, 1e-3)


def test_moon_phase():
    # Meeus example 48.a, 1992-04-12 0h
    phase = moon_phase(2448724.5)
    assert phase.illumination == approx(0.6786, 1e-3)
    assert phase.waxing
    assert phase.name == "Waxing Gibbous"


def test_find_crossings_finds_both_directions_and_refines_to_a_second():
    # A fake "altitude" that is a sine wave with a 1-day period, crossing 0 at 0.25 and 0.75 days.
    xs = find_crossings(lambda jd: 10 * math.cos(2 * math.pi * jd), 0, 1, 0)
    assert len(xs) == 2
    assert not xs[0].rising
    assert xs[0].jd == approx(0.25, 2.0 / 86400)
    assert xs[1].rising
    assert xs[1].jd == approx(0.75, 2.0 / 86400)
