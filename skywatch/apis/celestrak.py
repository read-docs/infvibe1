"""Satellite orbits (TLEs) from CelesTrak: https://celestrak.org/NORAD/documentation/gp-data-formats.php

CelesTrak blocks clients that download the same data more than once every 2
hours, so every set is cached in memory and on disk for 6 hours, and after a
failed download the last good copy is used. The ISS also has a fallback source
(SatNOGS, which mirrors Space-Track) for when CelesTrak is unreachable."""

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from skywatch.astro.sgp4 import Sgp4, Sgp4Error
from skywatch.astro.tle import parse_tle_file
from skywatch.http.client import HttpError, http_get, parse_json

_MAX_AGE_SECONDS = 6 * 3600
# After every source failed, wait this long before trying again, so a dead
# server doesn't add a timeout to every request.
_RETRY_AFTER_SECONDS = 10 * 60


@dataclass(frozen=True)
class SatelliteSet:
    satellites: list[Sgp4]
    fetched_unix: float  # when the TLEs were downloaded
    source: str  # where they came from


class _Source(NamedTuple):
    name: str
    url: str
    json: bool  # SatNOGS returns JSON instead of TLE text


def _build(tle_text: str, fetched: float, source: str) -> SatelliteSet:
    satellites = []
    for tle in parse_tle_file(tle_text):
        try:
            satellites.append(Sgp4(tle))
        except Sgp4Error:
            pass  # deep-space or broken elements: not something we track
    return SatelliteSet(satellites, fetched, source)


def _satnogs_to_tle(body: str) -> str:
    """SatNOGS JSON ([{tle0, tle1, tle2}, ...]) to TLE text."""
    arr = parse_json(body)
    if not isinstance(arr, list):
        return ""
    out = []
    for t in arr:
        name = str(t.get("tle0", ""))
        out.append(f"{name.removeprefix('0 ')}\n{t.get('tle1', '')}\n{t.get('tle2', '')}\n")
    return "".join(out)


class _Slot:
    """Per set (ISS, Starlink): a slow Starlink download must not stall ISS
    requests. Concurrent requests for the same set wait for one download."""

    def __init__(self):
        self.lock = threading.Lock()
        self.loaded: SatelliteSet | None = None
        self.last_failure = 0.0


class Celestrak:
    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._slots_lock = threading.Lock()  # guards _slots itself
        self._slots: dict[str, _Slot] = {}

    def iss(self) -> SatelliteSet:
        """Raises HttpError when no source works and nothing is cached."""
        return self._load(
            "iss",
            [
                _Source("CelesTrak", "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE", False),
                _Source("SatNOGS", "https://db.satnogs.org/api/tle/?norad_cat_id=25544&format=json", True),
            ],
        )

    def starlink(self) -> SatelliteSet:
        """Raises HttpError when no source works and nothing is cached."""
        return self._load(
            "starlink", [_Source("CelesTrak", "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=TLE", False)]
        )

    def _slot(self, key: str) -> _Slot:
        with self._slots_lock:
            return self._slots.setdefault(key, _Slot())

    def _load(self, key: str, sources: list[_Source]) -> SatelliteSet:
        s = self._slot(key)
        with s.lock:
            now = time.time()
            if s.loaded and now - s.loaded.fetched_unix < _MAX_AGE_SECONDS:
                return s.loaded

            # The disk copy survives restarts. Its first line is "# <fetched unix time> <source>".
            path = self._cache_dir / f"tle-{key}.txt"
            if s.loaded is None:
                try:
                    header, _, text = path.read_text().partition("\n")
                    hash_, fetched, source = header.split(maxsplit=2)
                    if hash_ == "#":
                        disk = _build(text, float(fetched), source.strip())
                        if disk.satellites:
                            s.loaded = disk
                        if s.loaded and now - disk.fetched_unix < _MAX_AGE_SECONDS:
                            return s.loaded
                except (OSError, ValueError):
                    pass

            if now - s.last_failure > _RETRY_AFTER_SECONDS:
                errors = []
                for src in sources:
                    try:
                        res = http_get(src.url)
                        if res.status != 200:
                            raise HttpError(res.status, f"HTTP {res.status}")
                        text = _satnogs_to_tle(res.body) if src.json else res.body
                        fresh = _build(text, now, src.name)
                        if not fresh.satellites:
                            raise HttpError(502, "no usable TLEs in the response")
                        try:
                            path.write_text(f"# {int(now)} {src.name}\n{text}")
                        except OSError:
                            pass
                        s.loaded = fresh
                        return fresh
                    except HttpError as e:
                        print(f"warning: {src.name} TLE download failed: {e}", file=sys.stderr)
                        errors.append(f"{src.name}: {e}")
                s.last_failure = now
                if s.loaded is None:
                    raise HttpError(502, f"couldn't download satellite orbits ({'; '.join(errors)})")
            if s.loaded is None:
                raise HttpError(502, "satellite orbit sources are unreachable; retrying in a few minutes")
            return s.loaded  # stale, but far better than nothing for a few days
