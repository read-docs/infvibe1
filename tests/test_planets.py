from helpers import approx

from skywatch.apis.open_meteo import Forecast, HourlyWeather
from skywatch.astro.planets import planet_position
from skywatch.services.planets import body_visibility, planets_report


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


NOON = 1792670400  # 2026-10-22 12:00 UTC, broad daylight in Warsaw


def gap_forecast() -> Forecast:
    """Overcast except 20:00-23:00 UTC."""
    return Forecast(
        "GMT",
        0,
        [HourlyWeather(NOON - 12 * 3600 + i * 3600.0, 0, 0.0 if 20 <= i < 23 else 100.0, 0, 0, 24000, 50, 0) for i in range(72)],
    )


def test_planets_report_lists_the_moon_and_seven_planets():
    report = planets_report(52.23, 21.01, NOON, None)
    bodies = report["bodies"]
    assert len(bodies) == 8
    assert bodies[0]["name"] == "Moon"
    assert bodies[7]["name"] == "Neptune"
    for b in bodies:
        assert not b["visible_now"]  # daytime
        for w in b["tonight"]:
            assert w["from"] <= w["to"]
            assert w["from"] > NOON
    assert not bodies[7]["naked_eye"]  # Neptune needs a telescope


def test_planets_report_hides_planets_behind_clouds():
    f = gap_forecast()
    report = planets_report(52.23, 21.01, NOON, f)
    assert report["weather"] is True
    # Saturn is high all evening, so the only clear window is the gap in the clouds.
    saturn = report["bodies"][5]
    assert saturn["name"] == "Saturn"
    assert saturn["high_tonight"] is True
    assert len(saturn["tonight"]) == 1
    assert saturn["tonight"][0]["from"] >= NOON - 12 * 3600 + 20 * 3600
    assert saturn["tonight"][0]["to"] < NOON - 12 * 3600 + 23 * 3600

    # Fully overcast: high tonight, but no window at all.
    for h in f.hours:
        h.cloud_low = 100
    cloudy = planets_report(52.23, 21.01, NOON, f)
    assert cloudy["bodies"][5]["high_tonight"] is True
    assert cloudy["bodies"][5]["tonight"] == []


def test_body_visibility():
    # high in a dark clear sky is perfect
    assert body_visibility(60, 0, -30, 0, 0) == (100, None)
    # below 10 degrees it can't be seen
    assert body_visibility(8, -2, -30, 0, 0) == (0, "too_low")
    # low down counts for less
    assert body_visibility(10, 0, -30, 0, 0).score == 40
    assert body_visibility(25, 0, -30, 0, 0).score == 70
    # bright planets show in twilight, faint ones need darkness
    assert body_visibility(40, -4.2, -6, 0, 0).score == 100  # Venus
    assert body_visibility(40, -2.0, -8, 0, 0).score == 50  # Jupiter, fading in
    assert body_visibility(40, 5.7, -8, 0, 0) == (0, "too_bright")  # Uranus
    assert body_visibility(40, 5.7, -21, 0, 0).score == 100
    # a few clouds dim it, a cloudy sky hides it
    assert body_visibility(40, 0, -30, 0.3, 0).score == 70
    assert body_visibility(40, 0, -30, 0.5, 0) == (0, "clouds")
    # moonlight dims only faint bodies
    assert body_visibility(40, -2, -30, 0, 1.0).score == 100
    assert body_visibility(40, 7.8, -30, 0, 1.0) == (50, "moonlight")  # Neptune


def test_planets_report_rates_each_body_hour_by_hour():
    report = planets_report(52.23, 21.01, NOON, gap_forecast())
    for b in report["bodies"]:
        assert len(b["hours"]) >= 13  # sunset to sunrise
        for h in b["hours"]:
            clear = NOON + 8 * 3600 <= h["time"] < NOON + 11 * 3600
            if not clear:
                assert h["score"] == 0
            if h["alt"] < 10:
                assert h["score"] == 0
        # The best hour can only be in the gap in the clouds.
        if b["best"] is not None:
            assert NOON + 8 * 3600 <= b["best"]["time"] < NOON + 11 * 3600
    saturn = report["bodies"][5]
    assert saturn["best"]["score"] > 50

    # Without a forecast, clouds are ignored and the hours still come back.
    no_weather = planets_report(52.23, 21.01, NOON, None)
    assert len(no_weather["bodies"][5]["hours"]) == len(saturn["hours"])
    assert no_weather["bodies"][5]["best"]["score"] >= saturn["best"]["score"]
