cmake_minimum_required(VERSION 3.20)
project(skywatch CXX)
cmake_policy(SET CMP0135 NEW)  # FetchContent: stamp extracted files with the extraction time

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(APPLE AND NOT OPENSSL_ROOT_DIR)
  execute_process(COMMAND brew --prefix openssl
                  OUTPUT_VARIABLE OPENSSL_ROOT_DIR
                  OUTPUT_STRIP_TRAILING_WHITESPACE)
endif()
find_package(OpenSSL REQUIRED)

include(FetchContent)
FetchContent_Declare(httplib
  URL https://github.com/yhirose/cpp-httplib/archive/refs/tags/v0.63.0.tar.gz)
FetchContent_Declare(json
  URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz)
# doctest is a single header; download just that file.
FetchContent_Declare(doctest
  URL https://raw.githubusercontent.com/doctest/doctest/v2.4.12/doctest/doctest.h
  DOWNLOAD_NO_EXTRACT TRUE)
set(HTTPLIB_REQUIRE_OPENSSL ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(httplib json doctest)

# Everything except main(), so the tests can link against it.
add_library(skywatch_core STATIC
  src/Config.cpp
  src/http/HttpClient.cpp
  src/apis/NasaApod.cpp
  src/apis/OpenMeteo.cpp
  src/apis/Geocoding.cpp
  src/apis/Celestrak.cpp
  src/apis/WhereTheIss.cpp
  src/apis/Swpc.cpp
  src/astro/time.cpp
  src/astro/coords.cpp
  src/astro/sun_moon.cpp
  src/astro/planets.cpp
  src/astro/tle.cpp
  src/astro/sgp4.cpp
  src/astro/passes.cpp
  src/services/SkyQuality.cpp
  src/services/Planets.cpp
  src/services/Iss.cpp
  src/services/Starlink.cpp
  src/services/Aurora.cpp
)
target_include_directories(skywatch_core PUBLIC src)
target_link_libraries(skywatch_core PUBLIC httplib::httplib nlohmann_json::nlohmann_json)
target_compile_options(skywatch_core PRIVATE -Wall -Wextra)

add_executable(skywatch src/main.cpp)
target_link_libraries(skywatch PRIVATE skywatch_core)
target_compile_definitions(skywatch PRIVATE
  SKYWATCH_ROOT="${CMAKE_SOURCE_DIR}")
target_compile_options(skywatch PRIVATE -Wall -Wextra)

add_executable(skywatch_tests
  tests/test_main.cpp
  tests/test_time.cpp
  tests/test_sun_moon.cpp
  tests/test_planets.cpp
  tests/test_sgp4.cpp
  tests/test_starlink.cpp
  tests/test_aurora.cpp
  tests/test_sky_quality.cpp
)
target_include_directories(skywatch_tests PRIVATE ${doctest_SOURCE_DIR})
target_link_libraries(skywatch_tests PRIVATE skywatch_core)

enable_testing()
add_test(NAME skywatch_tests COMMAND skywatch_tests)
