cmake_minimum_required(VERSION 3.13)
project(nvg_renderer C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# --- Lua 5.4 (vendored) ---
file(GLOB LUA_SRC
  third_party/lua/src/*.c
)
# Exclude lua.c and luac.c (they have main()).
list(FILTER LUA_SRC EXCLUDE REGEX ".*/(lua|luac)\\.c$")
add_library(lua_static STATIC ${LUA_SRC})
target_include_directories(lua_static PUBLIC third_party/lua/src)
target_compile_definitions(lua_static PUBLIC LUA_USE_LINUX)
target_link_libraries(lua_static PUBLIC m dl)

# --- nanovg ---
add_library(nanovg STATIC third_party/nanovg/nanovg.c)
target_include_directories(nanovg PUBLIC third_party/nanovg)

# --- OSMesa ---
find_package(PkgConfig REQUIRED)
pkg_check_modules(OSMESA REQUIRED osmesa)

# --- Renderer ---
add_executable(nvg_renderer
  src/main.c
  src/lua_nvg.c
  src/png_writer.c
)
target_include_directories(nvg_renderer PRIVATE
  src
  third_party/nanovg
  third_party/stb
  ${OSMESA_INCLUDE_DIRS}
)
target_link_libraries(nvg_renderer PRIVATE
  nanovg lua_static
  ${OSMESA_LIBRARIES}
  m
)
target_compile_options(nvg_renderer PRIVATE -Wall -Wno-unused-function -Wno-unused-parameter)
