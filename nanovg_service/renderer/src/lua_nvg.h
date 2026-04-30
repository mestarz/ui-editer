#ifndef LUA_NVG_H
#define LUA_NVG_H

#include "lua.h"
#include "lualib.h"
#include "lauxlib.h"
#include "nanovg.h"

/* Register all nvg* functions and NVG_* constants on the global table.
   Stores the NVGcontext pointer as global "vg" (lightuserdata). */
void lua_nvg_open(lua_State *L, NVGcontext *vg);

#endif
