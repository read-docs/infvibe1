import dataclasses

from helpers import approx

from skywatch.apis.open_meteo import Forecast, HourlyWeather
from skywatch.services.json_util import iround
from skywatch.services.sky_quality import hour_score, sky_condition, sky_report


def clear_sky(time: float = 0) -> HourlyWeather:
    return HourlyWeather(time, 0, 0, 0, 0, 24000, 50, 0)


def clear_forecast(start_unix: float) -> Forecast:
    """Hourly clear-sky forecast covering three days from start_unix."""
    return Forecast("GMT", 0, [clear_sky(start_unix + i * 3600) for i in range(72)])


def test_clear_dark_moonless_sky_is_perfect():
    assert hour_score(clear_sky(), -30, -10, 1.0) == 100


def test_daylight_and_civil_twilight_score_zero():
    assert hour_score(clear_sky(), 20, -10, 0) == 0
    assert hour_score(clear_sky(), -5, -10, 0) == 0


def test_twilight_halves_the_score_at_minus_6_and_fades_in_by_minus_18():
    assert hour_score(clear_sky(), -6, -10, 0) == 50
    assert hour_score(clear_sky(), -12, -10, 0) == 75
    assert hour_score(clear_sky(), -18, -10, 0) == 100


def test_overcast_low_cloud_blocks_everything():
    assert hour_score(dataclasses.replace(clear_sky(), cloud_low=100), -30, -10, 0) == 0


def test_high_cirrus_blocks_only_half():
    assert hour_score(dataclasses.replace(clear_sky(), cloud_high=100), -30, -10, 0) == 50


def test_a_full_moon_above_the_horizon_costs_25_points():
    assert hour_score(clear_sky(), -30, 20, 1.0) == 75
    assert hour_score(clear_sky(), -30, 20, 0.5) == 88  # 87.5 rounds up


def test_haze_humidity_and_rain_chance():
    w = dataclasses.replace(clear_sky(), visibility_m=12000, humidity=90, precip_probability=50)
    assert hour_score(w, -30, -10, 0) == 73  # 100 - 7.5 haze - 10 humidity - 10 rain


def test_sky_condition():
    assert sky_condition(0.0) == "clear"
    assert sky_condition(0.3) == "mostly_clear"
    assert sky_condition(0.5) == "cloudy"
    assert sky_condition(0.9) == "overcast"


def test_sky_report_rates_the_whole_night_by_its_dark_hours():
    now = 1792670400  # Warsaw, 2026-10-22 12:00 UTC
    forecast = clear_forecast(now - 12 * 3600)
    # Overcast until 23:00 UTC, clear after.
    for h in forecast.hours:
        if h.time < now + 11 * 3600:
            h.cloud_low = 100
    report = sky_report(forecast, 52.23, 21.01, now)
    q = report["night_quality"]
    dark = clear = total = 0
    for h in report["hours"]:
        overcast = h["time"] < now + 11 * 3600
        assert h["sky"] == ("overcast" if overcast else "clear")
        if not h["dark"]:
            continue
        dark += 1
        clear += not overcast
        total += h["score"]
    assert q["dark_hours"] == dark
    assert q["clear_hours"] == clear
    assert 0 < clear < dark
    assert q["percent"] == iround(total / dark)


def test_sky_report_for_an_ordinary_night():
    # Warsaw, 2026-10-22 12:00 UTC
    now = 1792670400
    report = sky_report(clear_forecast(now - 12 * 3600), 52.23, 21.01, now)

    night = report["night"]
    assert night["polar"] is None
    sunset, sunrise = night["sunset"], night["sunrise"]
    assert sunset > now
    assert sunrise > sunset
    assert (sunrise - sunset) / 3600 == approx(13.5, 0.03)  # late October: ~13.5 h of night

    civil, astro = night["twilight"]["civil"]["dusk"], night["twilight"]["astronomical"]["dusk"]
    assert civil > sunset
    assert astro > civil

    hours = report["hours"]
    assert len(hours) >= 13
    assert hours[0]["time"] <= sunset
    assert hours[-1]["time"] <= sunrise
    assert report["best"] is not None
    assert report["best"]["score"] > 0


def test_sky_report_at_the_nights_start_counts_the_current_hour_as_still_ahead():
    now = 1792670400 + 5 * 3600 + 1800  # 17:30 UTC, after sunset in Warsaw
    report = sky_report(clear_forecast(now - 12 * 3600), 52.23, 21.01, now)
    assert report["night"]["sunset"] < now
    for h in report["hours"]:
        assert h["past"] == (h["time"] + 3600 <= now)


def test_midnight_sun_in_tromso():
    now = 1782043200  # 2026-06-21 12:00 UTC
    report = sky_report(clear_forecast(now), 69.65, 18.96, now)
    assert report["night"]["polar"] == "day"
    assert report["best"] is None


def test_polar_night_in_tromso():
    now = 1797854400  # 2026-12-21 12:00 UTC
    report = sky_report(clear_forecast(now), 69.65, 18.96, now)
    assert report["night"]["polar"] == "night"
    assert report["best"] is not None
