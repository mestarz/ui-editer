cmake_minimum_required(VERSION 3.16)
project(librender_egl_lua_preview C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
add_compile_options(-Wall -Wextra -Wno-unused-parameter -Wno-unused-function)

# Headless OpenGL via EGL device platform (Mesa 26+, modern Linux).
# This sibling project replaces the OSMesa-based librender on systems where
# OSMesa is no longer shipped. The OSMesa build (../librender) is kept for
# WSL / Debian / older distros that still package libosmesa6-dev.
find_package(PkgConfig REQUIRED)
pkg_check_modules(EGL REQUIRED egl)
pkg_check_modules(GL  REQUIRED gl)

set(NANOVG_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/nanovg)
set(STB_DIR    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/stb)

add_library(nanovg STATIC ${NANOVG_DIR}/nanovg.c)
target_include_directories(nanovg PUBLIC ${NANOVG_DIR})

add_library(nvgrender SHARED src/render.c)
target_include_directories(nvgrender PRIVATE
  ${NANOVG_DIR} ${STB_DIR}
  ${EGL_INCLUDE_DIRS} ${GL_INCLUDE_DIRS})
target_link_libraries(nvgrender PRIVATE nanovg
  ${EGL_LIBRARIES} ${GL_LIBRARIES} m)
target_link_directories(nvgrender PRIVATE
  ${EGL_LIBRARY_DIRS} ${GL_LIBRARY_DIRS})
set_target_properties(nvgrender PROPERTIES
  OUTPUT_NAME "nvgrender"
  PREFIX "lib"
)
