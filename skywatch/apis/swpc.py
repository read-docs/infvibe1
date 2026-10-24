"""NOAA Space Weather Prediction Center: the planetary K index (Kp, 0-9), a
measure of geomagnetic activity. https://www.swpc.noaa.gov/products/planetary-k-index"""

import calendar
import re
from dataclasses import dataclass, field
from typing import NamedTuple

from skywatch.http.cache import Cache
from skywatch.http.client import HttpError, http_get, parse_json


class KpPoint(NamedTuple):
    time: float  # Unix seconds, start of the 3-hour interval
    kp: float
    kind: str  # "observed", "estimated" or "predicted"


@dataclass
class KpData:
    three_hour: list[KpPoint] = field(default_factory=list)  # last week observed + next 3 days predicted
    current: float | None = None  # latest 1-minute estimate


def _parse_time(s: str) -> float:
    """"2026-10-15T03:00:00" (UTC) -> Unix seconds, or 0 if it can't be read."""
    m = re.match(r"\s*([+-]?\d+)-([+-]?\d+)-([+-]?\d+)T([+-]?\d+):([+-]?\d+)(?::([+-]?\d+))?", s)
    if not m:
        return 0.0
    y, mo, d, h, mi = (int(g) for g in m.groups()[:5])
    sec = int(m.group(6) or 0)
    return float(calendar.timegm((y, mo, d, h, mi, sec, 0, 0, 0)))


def _number(v) -> float:
    if isinstance(v, bool):
        return -1.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return -1.0
    return -1.0


def _get_json(url: str) -> list:
    res = http_get(url)
    body = parse_json(res.body)
    if res.status != 200 or not isinstance(body, list):
        raise HttpError(res.status, f"NOAA SWPC returned HTTP {res.status}")
    return body


class Swpc:
    def __init__(self):
        self._cache = Cache(15 * 60)

    def fetch(self) -> KpData:
        """Raises HttpError if the 3-hour data can't be fetched; the 1-minute
        estimate is optional."""
        cached = self._cache.get("kp")
        if cached is not None:
            return cached

        data = KpData()
        for row in _get_json("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"):
            # Current format: objects. Older format: arrays with a header row first.
            if isinstance(row, dict):
                data.three_hour.append(
                    KpPoint(_parse_time(str(row.get("time_tag", ""))), _number(row.get("kp")), str(row.get("observed", "")))
                )
            elif isinstance(row, list) and len(row) >= 3 and row[1] != "kp":
                data.three_hour.append(KpPoint(_parse_time(str(row[0])), _number(row[1]), str(row[2])))
        if not data.three_hour:
            raise HttpError(502, "NOAA SWPC returned no Kp data")

        try:
            latest = _get_json("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json")
            if latest:
                current = float(latest[-1].get("estimated_kp", -1.0))
                data.current = current if current >= 0 else None
        except Exception:
            pass  # the 3-hour values are enough
        self._cache.put("kp", data)
        return data
