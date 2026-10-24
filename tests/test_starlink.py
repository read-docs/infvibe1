from skywatch.apis.celestrak import SatelliteSet
from skywatch.astro.sgp4 import Sgp4
from skywatch.astro.tle import parse_tle_file
from skywatch.services.starlink import starlink_report


def sample_set() -> SatelliteSet:
    # Real Starlink TLEs (via SatNOGS) from October 2026.
    tles = parse_tle_file(
        "STARLINK-3100\n"
        "1 49144U 21082Q   26295.16668980  .00038120  00000-0  22380-2 0  9994\n"
        "2 49144  70.0014  83.1836 0003596 259.3597  48.0136 15.11538324  5750\n"
        "STARLINK-4410\n"
        "1 53204U 22084R   26295.13490705 -.00002025  00000-0 -53839-4 0  9996\n"
        "2 53204  97.4042 359.3313 0002149  98.9058 261.2429 15.36976873234510\n"
        "STARLINK-4400\n"
        "1 53468U 22099D   26294.89363771  .00002503  00000-0  79843-4 0  9990\n"
        "2 53468  97.2868  48.1858 0001370  88.9613 271.1787 15.33441765230094\n"
    )
    return SatelliteSet([Sgp4(t) for t in tles], 0, "test")


def test_starlink_report_counts_and_groups_satellites():
    now = 1792670400  # 2026-10-22 12:00 UTC
    report = starlink_report(sample_set(), 52.23, 21.01, now)
    assert report["counts"]["total"] == 3
    assert report["sky_dark"] is False  # noon in Warsaw
    assert report["counts"]["visible"] == 0
    assert len(report["satellites"]) == report["counts"]["above_horizon"]

    # Newest launch first: 2022-099, 2022-084, 2021-082.
    recent = report["recent_launches"]
    assert len(recent) == 3
    assert recent[0]["launch"] == "2022-099"
    assert recent[2]["launch"] == "2021-082"
    assert recent[0]["train"] is False  # ~530 km: already at its working altitude


def test_starlink_report_sees_satellites_overhead_over_a_whole_day():
    # Polar orbits pass over every latitude, so within a day some satellite rises.
    sats = sample_set()
    seen = sum(
        starlink_report(sats, 52.23, 21.01, 1792670400 + m * 60.0)["counts"]["above_horizon"]
        for m in range(0, 24 * 60, 5)
    )
    assert seen > 0
