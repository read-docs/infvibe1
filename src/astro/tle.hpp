#pragma once

#include <string>
#include <vector>

// Two-line element sets (TLEs), the orbit format published by CelesTrak:
// https://celestrak.org/NORAD/documentation/tle-fmt.php
namespace astro {

struct Tle {
    std::string name;         // line 0 when present, else the catalogue number
    int catalogNumber;
    std::string intlDesignator;  // "98067A": launch year, launch number, piece
    double epochJd;           // Julian Date of the elements
    double bstar;             // drag term, 1/earth radii
    double inclinationDeg;
    double raanDeg;           // right ascension of the ascending node
    double eccentricity;
    double argPerigeeDeg;
    double meanAnomalyDeg;
    double meanMotionRevPerDay;
};

// Parses one TLE from its two data lines (69 characters each; anything after
// column 69 is ignored). Throws std::invalid_argument on malformed input.
Tle parseTle(const std::string& line1, const std::string& line2, const std::string& name = "");

// Parses CelesTrak's text format: optional name lines followed by line 1 and
// line 2. Malformed entries are skipped.
std::vector<Tle> parseTleFile(const std::string& text);

}  // namespace astro
