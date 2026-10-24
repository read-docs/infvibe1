"""NOAA Space Weather Prediction Center: the planetary K index (Kp, 0-9), a
measure of geomagnetic activity. https://www.swpc.noaa.gov/products/planetary-k-index"""

from dataclasses import dataclass, field
from typing import NamedTuple


class KpPoint(NamedTuple):
    time: float  # Unix seconds, start of the 3-hour interval
    kp: float
    kind: str  # "observed", "estimated" or "predicted"


@dataclass
class KpData:
    three_hour: list[KpPoint] = field(default_factory=list)  # last week observed + next 3 days predicted
    current: float | None = None  # latest 1-minute estimate
