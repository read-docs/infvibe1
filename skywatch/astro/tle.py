"""Two-line element sets (TLEs), the orbit format published by CelesTrak:
https://celestrak.org/NORAD/documentation/tle-fmt.php"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tle:
    name: str  # line 0 when present, else the catalogue number
    catalog_number: int
    intl_designator: str  # "98067A": launch year, launch number, piece
    epoch_jd: float  # Julian Date of the elements
    bstar: float  # drag term, 1/earth radii
    inclination_deg: float
    raan_deg: float  # right ascension of the ascending node
    eccentricity: float
    arg_perigee_deg: float
    mean_anomaly_deg: float
    mean_motion_rev_per_day: float


def _field(line: str, col: int, length: int) -> float:
    f = line[col : col + length].strip()
    if not f:
        return 0.0
    try:
        return float(f)
    except ValueError:
        raise ValueError(f"bad TLE field: {f}") from None


def _exp_field(line: str, col: int) -> float:
    """TLE "assumed decimal point" exponent notation: " 12345-3" means 0.12345e-3."""
    f = line[col : col + 8]
    mantissa = _field(f, 1, 5) / 1e5
    if f[:1] == "-":
        mantissa = -mantissa
    exponent = int(_field(f, 6, 2))
    return mantissa * 10.0**exponent


def _jd_jan1(year: int) -> float:
    """Julian Date of 0h UT on 1 January of the given year."""
    y = year - 1
    return 1721425.5 + 365.0 * y + y // 4 - y // 100 + y // 400


def parse_tle(line1: str, line2: str, name: str = "") -> Tle:
    """Parses one TLE from its two data lines (69 characters each; anything
    after column 69 is ignored). Raises ValueError on malformed input."""
    l1, l2 = line1.strip(), line2.strip()
    if len(l1) < 69 or len(l2) < 69 or l1[0] != "1" or l2[0] != "2":
        raise ValueError("not a TLE")
    try:
        catalog_number = int(_field(l1, 2, 5))
        yy = int(_field(l1, 18, 2))
        year = 2000 + yy if yy < 57 else 1900 + yy  # Sputnik launched in 1957
        day_of_year = _field(l1, 20, 12)
        return Tle(
            name=name.strip() or str(catalog_number),
            catalog_number=catalog_number,
            intl_designator=l1[9:17].strip(),
            epoch_jd=_jd_jan1(year) + day_of_year - 1,
            bstar=_exp_field(l1, 53),
            inclination_deg=_field(l2, 8, 8),
            raan_deg=_field(l2, 17, 8),
            eccentricity=_field(l2, 26, 7) / 1e7,  # leading "0." is implied
            arg_perigee_deg=_field(l2, 34, 8),
            mean_anomaly_deg=_field(l2, 43, 8),
            mean_motion_rev_per_day=_field(l2, 52, 11),
        )
    except (ValueError, OverflowError):
        raise ValueError(f"malformed TLE for {name}") from None


def parse_tle_file(text: str) -> list[Tle]:
    """Parses CelesTrak's text format: optional name lines followed by line 1
    and line 2. Malformed entries are skipped."""
    out = []
    name = line1 = ""
    for line in text.split("\n"):
        line = line.removesuffix("\r")
        if line.startswith("1 ") and len(line) >= 69:
            line1 = line
        elif line.startswith("2 ") and line1:
            try:
                out.append(parse_tle(line1, line, name))
            except ValueError:
                pass
            line1 = name = ""
        elif line.strip():
            name = line
            line1 = ""
    return out
