from helpers import approx

from skywatch.astro.planets import planet_position


def test_venus_position():
    # Meeus example 33.a, 1992-12-20 0h. JPL's approximate elements are good
    # to about an arcminute for Venus.
    venus = planet_position("Venus", 2448976.5)
    assert venus.eq.ra_deg == approx(316.172725, 1e-4)  # ±0.03°
    assert venus.eq.dec_deg == approx(-18.888011, 1.5e-3)  # ±0.03°
    assert venus.distance_au == approx(0.910947, 1e-4)
    assert venus.sun_distance_au == approx(0.724604, 1e-4)
    # Meeus 41.a gives the phase angle as 72.96°.
    assert venus.phase_angle_deg == approx(72.96, 2e-3)


def test_planet_magnitudes_are_in_their_usual_ranges():
    jd = 2461336.0  # 2026-10-22 12:00 UTC
    assert planet_position("Venus", jd).magnitude < -3.5
    assert planet_position("Jupiter", jd).magnitude < -1.5
    saturn = planet_position("Saturn", jd).magnitude
    assert -0.5 < saturn < 1.5
    assert planet_position("Uranus", jd).magnitude == approx(5.7, 0.05)
    assert planet_position("Neptune", jd).magnitude == approx(7.8, 0.05)


def test_inner_planets_never_stray_far_from_the_sun():
    for jd in range(2461000, 2461400, 7):
        assert planet_position("Mercury", jd).elongation_deg < 28.5
        assert planet_position("Venus", jd).elongation_deg < 47.5
