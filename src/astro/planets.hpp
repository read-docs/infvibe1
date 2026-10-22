#pragma once

#include "astro/coords.hpp"

// Planet positions from JPL's approximate Keplerian elements (E. M. Standish,
// "Keplerian Elements for Approximate Positions of the Major Planets", table 1,
// valid 1800-2050) and visual magnitudes from Meeus chapter 41. Accurate to a
// few arcminutes, which is far below what matters for "where do I look".
namespace astro {

enum class Planet { Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune };
constexpr Planet kPlanets[] = {Planet::Mercury, Planet::Venus,  Planet::Mars,   Planet::Jupiter,
                               Planet::Saturn,  Planet::Uranus, Planet::Neptune};

const char* planetName(Planet p);

struct PlanetPosition {
    Equatorial eq;         // apparent geocentric, equinox of date
    double distanceAu;     // from Earth
    double sunDistanceAu;  // from the Sun
    double elongationDeg;  // angle between the planet and the Sun, seen from Earth
    double phaseAngleDeg;  // angle Sun-planet-Earth; 0 means fully lit
    double magnitude;
};
PlanetPosition planetPosition(Planet p, double jd);

Horizontal planetHorizontal(Planet p, double jd, double latDeg, double lonDeg);

// A planet is a point, so at rise/set only refraction (34') lifts it.
constexpr double kPlanetRiseSetAltDeg = -0.5667;

}  // namespace astro
