import pytest
from helpers import approx
from sgp4_vectors import SGP4_CASES

from skywatch.apis.open_meteo import Forecast, HourlyWeather
from skywatch.astro.coords import Geodetic, ecef_to_geodetic, geodetic_to_ecef, look_angles
from skywatch.astro.passes import ISS_STD_MAGNITUDE, find_passes
from skywatch.astro.sgp4 import Sgp4, Sgp4Error
from skywatch.astro.time import jd_from_unix, unix_from_jd
from skywatch.astro.tle import parse_tle, parse_tle_file
from skywatch.services.iss import iss_passes


def test_tle_parsing_iss():
    t = parse_tle(
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927",
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537",
        "ISS (ZARYA)",
    )
    assert t.name == "ISS (ZARYA)"
    assert t.catalog_number == 25544
    assert t.intl_designator == "98067A"
    # 2008 day 264.51782528 = 2008-09-20 12:25:40 UT.
    assert t.epoch_jd == approx(2454730.01782528, 1e-12)
    assert t.bstar == approx(-0.11606e-4)
    assert t.eccentricity == approx(0.0006703)
    assert t.mean_motion_rev_per_day == approx(15.72125391)


def test_tle_file_parsing_skips_junk_and_keeps_names():
    tles = parse_tle_file(
        "ISS (ZARYA)\r\n"
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927\r\n"
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537\r\n"
        "garbage\n"
        "1 too short\n"
        "2 too short\n"
    )
    assert len(tles) == 1
    assert tles[0].name == "ISS (ZARYA)"


@pytest.mark.parametrize("line1, line2, expected", SGP4_CASES, ids=[c[0][2:7] for c in SGP4_CASES])
def test_sgp4_matches_vallado_verification_vectors_to_a_metre(line1, line2, expected):
    sat = Sgp4(parse_tle(line1, line2))
    for t, x, y, z, vx, vy, vz in expected:
        r, v = sat.propagate(t)
        assert abs(r[0] - x) < 1e-3 and abs(r[1] - y) < 1e-3 and abs(r[2] - z) < 1e-3, t
        assert abs(v[0] - vx) < 1e-6 and abs(v[1] - vy) < 1e-6 and abs(v[2] - vz) < 1e-6, t


def test_sgp4_vectors_cover_all_near_earth_cases():
    assert sum(len(c[2]) for c in SGP4_CASES) > 100


def test_sgp4_agrees_with_the_sgp4_library():
    # Cross-check only: the app never uses the library.
    sgp4_api = pytest.importorskip("sgp4.api")
    l1 = "1 25544U 98067A   26294.95113894  .00010428  00000-0  19720-3 0  9990"
    l2 = "2 25544  51.6330  32.7943 0006789 293.2617  66.7657 15.48983994591404"
    ours = Sgp4(parse_tle(l1, l2))
    theirs = sgp4_api.Satrec.twoline2rv(l1, l2, sgp4_api.WGS72)
    for t in range(-1440, 4 * 1440, 97):
        r, _ = ours.propagate(t)
        err, r2, _ = theirs.sgp4_tsince(t)
        assert err == 0
        assert max(abs(a - b) for a, b in zip(r, r2)) < 1e-3, t


def test_sgp4_rejects_deep_space_orbits():
    # Molniya 2-14: a 12-hour orbit.
    molniya = parse_tle(
        "1 08195U 75081A   06176.33215444  .00000099  00000-0  11873-3 0   813",
        "2 08195  64.1586 279.0717 6877146 264.7651  20.2257  2.00491383225656",
    )
    with pytest.raises(Sgp4Error):
        Sgp4(molniya)


def test_earth_fixed_conversions_round_trip():
    g = Geodetic(52.23, 21.01, 420)
    back = ecef_to_geodetic(geodetic_to_ecef(g))
    assert back.lat_deg == approx(g.lat_deg, 1e-9)
    assert back.lon_deg == approx(g.lon_deg, 1e-9)
    assert back.alt_km == approx(g.alt_km, 1e-6)
    # Straight overhead.
    look = look_angles(geodetic_to_ecef(g), Geodetic(52.23, 21.01, 0))
    assert look.h.alt_deg == approx(90, 1e-6)
    assert look.range_km == approx(420, 1e-6)


ISS_2026 = (
    "1 25544U 98067A   26294.95113894  .00010428  00000-0  19720-3 0  9990",
    "2 25544  51.6330  32.7943 0006789 293.2617  66.7657 15.48983994591404",
)


def test_iss_pass_over_warsaw_matches_pyephem():
    iss = Sgp4(parse_tle(*ISS_2026))
    warsaw = Geodetic(52.23, 21.01, 0)
    start = jd_from_unix(1792723800)  # 2026-10-23 02:50 UTC
    passes = find_passes(iss, warsaw, start, start + 0.05, ISS_STD_MAGNITUDE)
    assert len(passes) == 1
    p = passes[0]
    # Reference: PyEphem's next_pass with the same TLE (rise/set at 0°, no refraction).
    assert unix_from_jd(p.rise.jd) == approx(1792724200.3, 3e-9)  # ±5 s
    assert unix_from_jd(p.peak.jd) == approx(1792724527.9, 3e-9)
    assert unix_from_jd(p.set.jd) == approx(1792724856.9, 3e-9)
    assert p.rise.az_deg == approx(248.46, 1e-3)
    assert p.peak.alt_deg == approx(61.715, 1e-3)
    assert p.set.az_deg == approx(80.94, 1e-3)
    # A dark morning sky: the ISS shows once it leaves Earth's shadow, just after the peak.
    assert p.visible
    assert p.visible_start is not None
    assert p.visible_start.jd > p.peak.jd
    assert p.brightest_magnitude < -3


def test_iss_passes_marks_a_visible_pass_under_clouds_as_not_clear():
    iss = Sgp4(parse_tle(*ISS_2026))
    start = 1792723800  # 2026-10-23 02:50 UTC; the visible pass starts ~03:02
    f = Forecast("GMT", 0, [HourlyWeather(start - 1800 + i * 3600.0, 100, 100, 0, 0, 24000, 90, 0) for i in range(-2, 4)])
    out = iss_passes(iss, Geodetic(52.23, 21.01, 0), start, 0.05, f)
    assert len(out["passes"]) == 1
    assert out["passes"][0]["visible"] is True
    assert out["passes"][0]["clear"] is False
    assert out["passes"][0]["cloud"] == 100

    # Without a forecast there is no cloud information at all.
    no_weather = iss_passes(iss, Geodetic(52.23, 21.01, 0), start, 0.05, None)
    assert "clear" not in no_weather["passes"][0]
