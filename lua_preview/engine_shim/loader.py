"""Lua require 重写：让 BaiSiYeShou/scripts/ 成为搜索根。

TapTap 引擎用纯 "Renderer"、"core.system.input.Input" 这种点号路径，
对应 scripts/Renderer.lua、scripts/core/system/input/Input.lua。
"""
import os


LUA_SEARCHER_TEMPLATE = r"""
package.path = ''
local function searcher(modname)
    local rel = modname:gsub('%.', '/')
    for _, base in ipairs(__lp_search_roots) do
        local candidates = { base..'/'..rel..'.lua', base..'/'..rel..'/init.lua' }
        for _, p in ipairs(candidates) do
            local f = io.open(p, 'r')
            if f then
                local src = f:read('*a')
                f:close()
                local chunk, err = load(src, '@'..p)
                if not chunk then error('Lua syntax: '..err) end
                return chunk
            end
        end
    end
    return '\n\tno file in __lp_search_roots for module \''..modname..'\''
end
package.searchers = { package.searchers[1], searcher }
package.loaders  = package.searchers
"""


def install(lua, *script_roots: str):
    g = lua.globals()
    g["__lp_search_roots"] = lua.table_from(
        {i + 1: os.path.abspath(p) for i, p in enumerate(script_roots)}
    )
    lua.execute(LUA_SEARCHER_TEMPLATE)
