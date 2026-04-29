// ============================================================
// server/lua-runtime.js  fengari 包装：加载 boot.lua + main.lua
// ============================================================
import { lua, lauxlib, lualib, to_luastring, to_jsstring } from 'fengari';
import path from 'node:path';
import fs from 'node:fs';

const GAME_ROOT = path.resolve(process.env.GAME_ROOT || path.join(process.cwd(), '../../BaiSiYeShou'));
const SCRIPTS   = path.join(GAME_ROOT, 'scripts');
const BOOT      = path.resolve(process.cwd(), 'server/recorder/boot.lua');

// 单例 Lua 状态
let L = null;
let _ready = false;

function dump_stack(L) {
  const top = lua.lua_gettop(L);
  for (let i = 1; i <= top; i++) {
    const t = lua.lua_typename(L, lua.lua_type(L, i));
    let v = '';
    try { v = to_jsstring(lua.lua_tolstring(L, i) || lua.lua_tostring(L, i) || []); } catch (_) {}
    console.log(`  [${i}] ${to_jsstring(t)} = ${v}`);
  }
}

function check(L, status, ctx) {
  if (status !== lua.LUA_OK) {
    const err = lua.lua_tostring(L, -1);
    const msg = err ? to_jsstring(err) : '<no msg>';
    lua.lua_pop(L, 1);
    throw new Error(`[Lua ${ctx}] ${msg}`);
  }
}

function dostring(L, src, name) {
  const status = lauxlib.luaL_loadbuffer(L, to_luastring(src), null, to_luastring(name));
  check(L, status, `load ${name}`);
  const callStatus = lua.lua_pcall(L, 0, lua.LUA_MULTRET, 0);
  check(L, callStatus, `exec ${name}`);
}

export function init() {
  if (_ready) return _do_init();
  return _do_init();
}

export function reload() {
  // 丢弃旧状态，重新创建 Lua state（fengari 的 close 通过 GC 处理）
  L = null;
  _ready = false;
  return _do_init();
}

function _do_init() {
  L = lauxlib.luaL_newstate();
  lualib.luaL_openlibs(L);

  // 设置 package.path 指向 game scripts/
  const pp = `${SCRIPTS}/?.lua;${SCRIPTS}/?/init.lua`;
  dostring(L,
    `package.path = ${JSON.stringify(pp)}; package.cpath = ""`,
    'set-path');

  // print 重定向（让 Lua print 走 console，方便调试）
  lua.lua_pushcfunction(L, (L) => {
    const n = lua.lua_gettop(L);
    const parts = [];
    for (let i = 1; i <= n; i++) {
      const s = lauxlib.luaL_tolstring(L, i);
      parts.push(to_jsstring(s));
      lua.lua_pop(L, 1);
    }
    console.log('[lua]', parts.join('\t'));
    return 0;
  });
  lua.lua_setglobal(L, to_luastring('print'));

  // 加载 boot.lua
  const bootSrc = fs.readFileSync(BOOT, 'utf-8');
  dostring(L, bootSrc, 'boot.lua');

  // boot.lua 已注入所有 stub 与 __recorder。现在 require "main"
  // 注：main.lua 顶层定义 Start() 函数为 _G，不自动执行。
  dostring(L, `__recorder.boot(); require "main"; Start()`, 'init-game');

  _ready = true;
  console.log('[lua-runtime] ready (game booted)');
}

export function reset_recorder() {
  dostring(L, `__recorder.reset()`, 'reset');
}

export function set_enabled(v) {
  dostring(L, `__recorder.set_enabled(${v ? 'true' : 'false'})`, 'set-enabled');
}

export function goto_scene(id) {
  // 不同场景需要不同的前置状态：
  //  - title/gallery/home/area_select: 直接 SM.GoTo 即可
  //  - party_select/explore/battle: 需要 areaId/party
  //  - base/placement/defense: 需要先 StartNewGame 再 EnterX
  // 使用 GameFlow 走完整链路最稳。
  const setup = `
    local SM = require "SceneManager"
    local GF = require "GameFlow"
    local GS = require "GameState"
    local CDB = require "core.data.db.CharacterDB"
    local id = ${JSON.stringify(id)}
    if id == "title" then GF.EnterTitle()
    elseif id == "gallery" then GF.EnterGallery()
    else
      -- 准备一份"已开局"状态：协议者 + 3 队友
      if not GS._editor_inited then
        GF.StartNewGame("civilian_f_1")
        GS._editor_inited = true
      end
      if id == "home" then GF.EnterHome()
      elseif id == "area_select" then GF.EnterAreaSelect()
      elseif id == "party_select" then GF.EnterPartySelect("downtown", "explore")
      elseif id == "explore" then
        local ids = {}
        for _, c in ipairs(GS.AllAliveCompanions and GS.AllAliveCompanions() or {}) do
          ids[#ids+1] = c.charId
          if #ids >= 3 then break end
        end
        GF.EnterExplore("downtown", ids)
      elseif id == "battle" then GF.EnterBattle({ enemies = {} })
      elseif id == "base" then GF.EnterBase()
      elseif id == "placement" then GF.EnterPlacement()
      elseif id == "defense" then GF.EnterDefense()
      else SM.GoTo(id)
      end
    end
  `;
  dostring(L, setup, `goto ${id}`);
}

export function fire_render() {
  dostring(L,
    `local ok, err = __recorder.fire_render(); if not ok then error(err) end`,
    'fire-render');
}

export function get_events() {
  // 用 Lua 序列化为 JSON 字符串。字符串字段用纯 JSON 转义以避免 %q 产生非 UTF-8 字节。
  dostring(L, `
    local function jstr(s)
      s = tostring(s or "")
      s = s:gsub('\\\\', '\\\\\\\\')
      s = s:gsub('"', '\\\\"')
      s = s:gsub('\\n', '\\\\n')
      s = s:gsub('\\r', '\\\\r')
      s = s:gsub('\\t', '\\\\t')
      -- 删除剩余控制字符（保险）
      s = s:gsub('[%z\\1-\\31]', '')
      return '"' .. s .. '"'
    end
    local function num(v) v = tonumber(v) or 0; return string.format("%.4f", v) end
    local function stack_json(st)
      if type(st) ~= "table" then return "[]" end
      local parts = {}
      for i, fr in ipairs(st) do
        parts[i] = "{" ..
          '"file":' .. jstr(fr.file) .. "," ..
          '"line":' .. tostring(tonumber(fr.line) or 0) .. "," ..
          '"name":' .. jstr(fr.name) .. "}"
      end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    local out = {}
    for i, ev in ipairs(__recorder.events) do
      out[i] = "{" ..
        '"type":'  .. jstr(ev.type)  .. "," ..
        '"api":'   .. jstr(ev.api)   .. "," ..
        '"x":'     .. num(ev.x)      .. "," ..
        '"y":'     .. num(ev.y)      .. "," ..
        '"w":'     .. num(ev.w)      .. "," ..
        '"h":'     .. num(ev.h)      .. "," ..
        '"depth":' .. tostring(ev.depth or 0) .. "," ..
        '"src":'   .. jstr(ev.src)   .. "," ..
        '"hint":'  .. jstr(ev.hint)  .. "," ..
        '"align":' .. jstr(ev.align) .. "," ..
        '"stack":' .. stack_json(ev.stack) .. "}"
    end
    __recorder._json = "[" .. table.concat(out, ",") .. "]"
  `, 'serialize');

  lua.lua_getglobal(L, to_luastring('__recorder'));
  lua.lua_getfield(L, -1, to_luastring('_json'));
  // 用 byte 数组取出，避免 fengari 自动 utf8 校验
  const buf = lua.lua_tolstring(L, -1);
  const s = Buffer.from(buf).toString('utf-8');
  lua.lua_pop(L, 2);
  const events = JSON.parse(s);
  // 规范化路径：把绝对 GAME_ROOT 前缀剥掉，让 src/stack[].file 都相对 BaiSiYeShou/
  const prefix = GAME_ROOT.endsWith('/') ? GAME_ROOT : GAME_ROOT + '/';
  const norm = (p) => (typeof p === 'string' && p.startsWith(prefix)) ? p.slice(prefix.length) : p;
  for (const ev of events) {
    if (ev.src) ev.src = norm(ev.src);
    if (Array.isArray(ev.stack)) {
      for (const fr of ev.stack) {
        if (fr.file) fr.file = norm(fr.file);
      }
    }
  }
  return events;
}

export function list_scenes() {
  // 解析 Registry.lua 文本（避免依赖运行时状态）
  const reg = fs.readFileSync(path.join(SCRIPTS, 'scenes', 'Registry.lua'), 'utf-8');
  const re = /\{\s*id\s*=\s*"([^"]+)"\s*,\s*module\s*=\s*"([^"]+)"/g;
  const out = [];
  let m;
  while ((m = re.exec(reg)) !== null) {
    out.push({ id: m[1], module: m[2] });
  }
  return out;
}
