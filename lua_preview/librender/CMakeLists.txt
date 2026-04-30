cmake_minimum_required(VERSION 3.16)
project(librender_lua_preview C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
add_compile_options(-Wall -Wextra -Wno-unused-parameter -Wno-unused-function)

# OSMesa (headless software OpenGL).
find_package(PkgConfig REQUIRED)
pkg_check_modules(OSMESA REQUIRED osmesa)

set(NANOVG_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/nanovg)
set(STB_DIR    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/stb)

add_library(nanovg STATIC ${NANOVG_DIR}/nanovg.c)
target_include_directories(nanovg PUBLIC ${NANOVG_DIR})

add_library(nvgrender SHARED src/render.c)
target_include_directories(nvgrender PRIVATE ${NANOVG_DIR} ${STB_DIR} ${OSMESA_INCLUDE_DIRS})
target_link_libraries(nvgrender PRIVATE nanovg ${OSMESA_LIBRARIES} m)
target_link_directories(nvgrender PRIVATE ${OSMESA_LIBRARY_DIRS})
set_target_properties(nvgrender PROPERTIES
  OUTPUT_NAME "nvgrender"
  PREFIX "lib"
)
