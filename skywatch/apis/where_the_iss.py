"""The ISS position published by https://wheretheiss.at, used only to check our
own SGP4 engine against an independent source."""

from typing import NamedTuple


class LiveIssPosition(NamedTuple):
    unix_time: float
    lat_deg: float
    lon_deg: float
    alt_km: float
