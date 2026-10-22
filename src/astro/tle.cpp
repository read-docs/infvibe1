#include "astro/tle.hpp"

#include <cmath>
#include <sstream>
#include <stdexcept>

#include "astro/time.hpp"

namespace astro {

namespace {

std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

double field(const std::string& line, size_t col, size_t len) {
    std::string f = trim(line.substr(col, len));
    if (f.empty()) return 0;
    size_t used = 0;
    double v = std::stod(f, &used);
    if (used != f.size()) throw std::invalid_argument("bad TLE field: " + f);
    return v;
}

// TLE "assumed decimal point" exponent notation: " 12345-3" means 0.12345e-3.
double expField(const std::string& line, size_t col) {
    std::string f = line.substr(col, 8);
    double mantissa = field(f, 1, 5) / 1e5;
    if (f[0] == '-') mantissa = -mantissa;
    int exponent = int(field(f, 6, 2));
    return mantissa * std::pow(10.0, exponent);
}

// Julian Date of 0h UT on 1 January of the given year.
double jdJan1(int year) {
    int y = year - 1;
    return 1721425.5 + 365.0 * y + y / 4 - y / 100 + y / 400;
}

}  // namespace

Tle parseTle(const std::string& line1In, const std::string& line2In, const std::string& name) {
    std::string l1 = trim(line1In), l2 = trim(line2In);
    if (l1.size() < 69 || l2.size() < 69 || l1[0] != '1' || l2[0] != '2') {
        throw std::invalid_argument("not a TLE");
    }
    try {
        Tle t;
        t.catalogNumber = int(field(l1, 2, 5));
        t.name = trim(name).empty() ? std::to_string(t.catalogNumber) : trim(name);
        t.intlDesignator = trim(l1.substr(9, 8));

        int yy = int(field(l1, 18, 2));
        int year = yy < 57 ? 2000 + yy : 1900 + yy;  // Sputnik launched in 1957
        double dayOfYear = field(l1, 20, 12);
        t.epochJd = jdJan1(year) + dayOfYear - 1;

        t.bstar = expField(l1, 53);
        t.inclinationDeg = field(l2, 8, 8);
        t.raanDeg = field(l2, 17, 8);
        t.eccentricity = field(l2, 26, 7) / 1e7;  // leading "0." is implied
        t.argPerigeeDeg = field(l2, 34, 8);
        t.meanAnomalyDeg = field(l2, 43, 8);
        t.meanMotionRevPerDay = field(l2, 52, 11);
        return t;
    } catch (const std::logic_error&) {
        throw std::invalid_argument("malformed TLE for " + name);
    }
}

std::vector<Tle> parseTleFile(const std::string& text) {
    std::vector<Tle> out;
    std::istringstream in(text);
    std::string line, name, line1;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.rfind("1 ", 0) == 0 && line.size() >= 69) {
            line1 = line;
        } else if (line.rfind("2 ", 0) == 0 && !line1.empty()) {
            try {
                out.push_back(parseTle(line1, line, name));
            } catch (const std::invalid_argument&) {
            }
            line1.clear();
            name.clear();
        } else if (!trim(line).empty()) {
            name = line;
            line1.clear();
        }
    }
    return out;
}

}  // namespace astro
