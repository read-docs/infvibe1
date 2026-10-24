"""Satellite orbits (TLEs) from CelesTrak: https://celestrak.org/NORAD/documentation/gp-data-formats.php"""

from dataclasses import dataclass

from skywatch.astro.sgp4 import Sgp4


@dataclass(frozen=True)
class SatelliteSet:
    satellites: list[Sgp4]
    fetched_unix: float  # when the TLEs were downloaded
    source: str  # where they came from
