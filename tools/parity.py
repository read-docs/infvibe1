"""Compares the C++ and Python servers endpoint by endpoint.

Start both first:
    ./build/skywatch                       # C++ on :8080
    python3 -m skywatch --port 8081        # Python on :8081
then run:
    python3 tools/parity.py [--cpp URL] [--py URL]

Each endpoint is requested from both servers at the same moment. The JSON must
have the same structure (keys, array lengths, types); values may differ by
small tolerances, since the two requests run a few milliseconds apart.
Exits with 1 if any difference is found."""

import argparse
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PLACES = {
    "Cairo": (30.04, 31.24),
    "Warsaw": (52.23, 21.01),
    "Tromso": (69.65, 18.96),  # polar day/night
    "Sydney": (-33.87, 151.21),
    "0,0": (0, 0),
}

TIME_TOLERANCE_S = 5  # crossings are refined to ~1 s; "now" differs by a fraction of a second
ANGLE_TOLERANCE = 0.2  # degrees; the ISS moves ~0.07° per second
SCORE_TOLERANCE = 1


def urls() -> list[str]:
    out = ["/api/health", "/api/iss/track", "/api/iss/track?minutes=10", "/api/iss/now", "/api/geocode?q=Warsaw",
           "/api/apod?date=2025-06-01", "/api/apod?date=2026-10-20"]
    for lat, lon in PLACES.values():
        q = f"lat={lat}&lon={lon}"
        out += [f"/api/sky?{q}", f"/api/planets?{q}", f"/api/iss/now?{q}", f"/api/iss/passes?{q}",
                f"/api/iss/passes?{q}&days=10", f"/api/starlink?{q}", f"/api/aurora?{q}"]
    # Error cases: the status and the message must match too.
    out += ["/api/sky?lat=abc&lon=1", "/api/sky?lat=&lon=1", "/api/sky?lat=1x&lon=1", "/api/sky?lat=91&lon=1",
            "/api/sky?lon=1", "/api/sky?lat=%205&lon=1", "/api/sky?lat=5%20&lon=1", "/api/planets?lat=0x10&lon=1",
            "/api/iss/now?lat=52", "/api/iss/track?minutes=0", "/api/iss/passes?lat=1&lon=1&days=11",
            "/api/geocode?q=a", "/api/geocode", "/api/apod?date=yesterday", "/api/apod?date=1990-01-01"]  # fmt: skip
    return out


def fetch(base: str, path: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(base + path, timeout=120) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body.decode(errors="replace")


def tolerance(key: str, a: float, b: float) -> float:
    if isinstance(a, int) and isinstance(b, int) and abs(a) > 1e9:
        return TIME_TOLERANCE_S  # Unix times
    if key in ("score", "percent", "cloud", "cloud_blocking"):
        return SCORE_TOLERANCE
    if key in ("lat", "lon", "alt", "az", "sun_alt", "moon_alt", "max_alt", "geomagnetic_lat", "elongation"):
        return ANGLE_TOLERANCE
    if key in ("range_km", "alt_km", "mean_alt_km", "distance_km"):
        return 2.0  # the ISS moves 7.7 km/s, but mostly sideways
    if key == "difference_km":
        return 1.0
    if key == "age_hours":
        return 0.1
    return max(0.15, 1e-3 * max(abs(a), abs(b)))


def compare(a, b, path: str, key: str, diffs: list[str]) -> None:
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or a is None or b is None:
        if a != b:
            diffs.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, int) != isinstance(b, int):
            diffs.append(f"{path}: int/float mismatch {a!r} vs {b!r}")
        elif abs(a - b) > tolerance(key, a, b):
            diffs.append(f"{path}: {a} vs {b}")
    elif isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            diffs.append(f"{path}: keys {sorted(a.keys() ^ b.keys())} differ")
        for k in a.keys() & b.keys():
            compare(a[k], b[k], f"{path}.{k}", k, diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: {len(a)} items vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, f"{path}[{i}]", key, diffs)
    else:
        diffs.append(f"{path}: type {type(a).__name__} vs {type(b).__name__}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpp", default="http://127.0.0.1:8080")
    parser.add_argument("--py", default="http://127.0.0.1:8081")
    args = parser.parse_args()

    failed = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        for path in urls():
            cpp, py = pool.map(lambda base: fetch(base, path), (args.cpp, args.py))
            diffs: list[str] = []
            if cpp[0] != py[0]:
                diffs.append(f"status {cpp[0]} vs {py[0]}")
            compare(cpp[1], py[1], "$", "", diffs)
            print(f"{'OK  ' if not diffs else 'DIFF'} {cpp[0]} {path}")
            for d in diffs[:10]:
                print(f"       {d}")
            if len(diffs) > 10:
                print(f"       ... and {len(diffs) - 10} more")
            failed += bool(diffs)
    print(f"\n{failed} of {len(urls())} endpoints differ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
