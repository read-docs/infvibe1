import dataclasses

from helpers import approx

from skywatch.apis.open_meteo import Forecast, HourlyWeather
from skywatch.apis.swpc import KpData, KpPoint
from skywatch.services.aurora import aurora_chance, aurora_report, geomagnetic_latitude


def test_geomagnetic_latitude():
    # On the dipole axis and its antipode.
    assert geomagnetic_latitude(80.8, -72.8) == approx(90)
    assert geomagnetic_latitude(-80.8, 107.2) == approx(-90)
    # Europe sits nearer the magnetic equator than North America at the same latitude.
    warsaw = geomagnetic_latitude(52.23, 21.01)
    winnipeg = geomagnetic_latitude(49.9, -97.1)
    assert warsaw == approx(50.4, 0.02)
    assert winnipeg > warsaw + 5


def test_aurora_chance_by_kp():
    tromso = geomagnetic_latitude(69.65, 18.96)  # ~67°: under the oval
    assert aurora_chance(1, tromso) == "overhead"
    warsaw = geomagnetic_latitude(52.23, 21.01)
    assert aurora_chance(2, warsaw) == "none"
    assert aurora_chance(5, warsaw) == "horizon"
    assert aurora_chance(9, warsaw) == "overhead"
    assert aurora_chance(-1, warsaw) == "none"  # no data


def test_aurora_report_combines_kp_darkness_and_clouds():
    noon = 1792670400  # 2026-10-22 12:00 UTC
    kp = KpData([KpPoint(noon + i * 3 * 3600.0, 6.0, "predicted") for i in range(-8, 24)], 5.67)
    clear = Forecast("GMT", 0, [HourlyWeather(noon - 12 * 3600 + i * 3600.0, 0, 0, 0, 0, 24000, 50, 0) for i in range(72)])

    report = aurora_report(kp, clear, 52.23, 21.01, noon)
    assert report["location"]["look_towards"] == "north"
    assert report["kp_needed"]["horizon"] == approx(4.8, 0.05)
    assert report["tonight"]["verdict"] == "go"
    assert report["tonight"]["best"]["chance"] == "horizon"
    assert report["now"]["kp"] == 5.67

    overcast = Forecast("GMT", 0, [dataclasses.replace(h, cloud_low=100) for h in clear.hours])
    assert aurora_report(kp, overcast, 52.23, 21.01, noon)["tonight"]["verdict"] == "cloudy"

    # Southern hemisphere looks south.
    assert aurora_report(kp, clear, -42.9, 147.3, noon)["location"]["look_towards"] == "south"
