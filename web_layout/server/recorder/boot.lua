-- ============================================================
-- web_layout/server/recorder/boot.lua
-- 在 require "main" 之前注入：
--  1. 引擎全局 stub（nvg*/graphics/input/Scene/SubscribeToEvent/cache/cjson/File）
--  2. Renderer 拦截器（package.preload["Renderer"]）
--  3. 暴露 __recorder 给 JS 端读
-- ============================================================

-- ---------- 全局录制状态 ----------
__recorder = {
    events  = {},     -- 顺序记录每次绘制 { type=, x=, y=, w=, h=, depth=, src=, hint= }
    depth   = 0,      -- nvgSave 嵌套深度（用于推断父子）
    enabled = false,  -- 由 JS 在 Draw 前后切换
}

local function rec(ev) end  -- forward declaration; redefined below

local function caller_src()
    local info = debug.getinfo(3, "Sl")
    if not info then return "?:0" end
    local s = info.source or "?"
    if s:sub(1, 1) == "@" then s = s:sub(2) end
    return s .. ":" .. (info.currentline or 0)
end

-- 抓取完整调用栈（跳过 boot.lua 自己），返回数组形式 {file, line, name}
local function caller_stack()
    local stack = {}
    for level = 3, 30 do
        local info = debug.getinfo(level, "Snl")
        if not info then break end
        local s = info.source or "?"
        if s:sub(1, 1) == "@" then s = s:sub(2) end
        if s:find("boot%.lua") or s == "?" or s == "=[C]" or s:sub(1,1) == "[" then
            -- 跳过 boot 内部 / C 函数
        else
            stack[#stack + 1] = {
                file = s,
                line = info.currentline or 0,
                name = info.name or info.what or "?",
                kind = info.what or "?",
            }
        end
        if #stack >= 8 then break end
    end
    return stack
end

rec = function(ev)
    if not __recorder.enabled then return end
    ev.depth = __recorder.depth
    if not ev.stack then ev.stack = caller_stack() end
    __recorder.events[#__recorder.events + 1] = ev
end

-- ---------- 引擎全局 stub ----------
local function noop() end
local function zero() return 0 end

graphics = setmetatable({ _w = 1280, _h = 720, _dpr = 1.0 }, { __index = function() return function() return 0 end end })
function graphics:GetWidth()  return self._w end
function graphics:GetHeight() return self._h end
function graphics:GetDPR()    return self._dpr end

input = setmetatable({
    mousePosition = { x = 0, y = 0 },
}, { __index = function() return function() return false end end })
function input:GetKeyDown()        return false end
function input:GetKeyPress()       return false end
function input:GetMouseButtonDown() return false end
function input:GetMouseButtonPress() return false end

cache = { GetResource = function() return setmetatable({}, { __index = function() return noop end }) end }
fileSystem = { FileExists = function(_, p)
    -- 让 settings.json 这类不存在的可选文件返回 false（main.lua 走默认值）
    return false
end }

-- File 类：只支持 ReadString/WriteString；写入完全忽略（避免 Settings.Save 写穿主仓库）
File = function(path, mode)
    return {
        IsOpen      = function() return false end,
        ReadString  = function() return "" end,
        WriteString = function() end,
        Close       = function() end,
    }
end

-- cjson stub（仅 Settings 模块用）
cjson = {
    encode = function(t) return "{}" end,
    decode = function(s) return {} end,
}

-- Scene + 组件（SFX.Init 用）
Scene = function()
    return setmetatable({
        CreateChild     = function() return Scene() end,
        CreateComponent = function() return setmetatable({
            soundType = "", gain = 1.0, autoRemoveMode = 0,
            Play = noop,
        }, { __index = function() return noop end }) end,
    }, { __index = function() return noop end })
end

-- 事件订阅：仅捕获 HandleRender / HandleUpdate，供 JS 触发
__recorder.handlers = {}
function SubscribeToEvent(a, b, c)
    -- 两种调用形式：
    --   SubscribeToEvent(vg, "NanoVGRender", "HandleRender")
    --   SubscribeToEvent("Update", "HandleUpdate")
    local evName, fnName
    if type(a) == "string" then
        evName, fnName = a, b
    else
        evName, fnName = b, c
    end
    __recorder.handlers[evName] = fnName
end

function UnsubscribeFromEvent() end

-- ---------- nvg* 全套 stub ----------
-- 所有 nvg* 仅维护变换栈与必要返回值；不做任何录制
local _xform_stack = {}
local _cur_xform   = { 1, 0, 0, 1, 0, 0 }

local function _push_xform()
    _xform_stack[#_xform_stack + 1] = { _cur_xform[1], _cur_xform[2], _cur_xform[3], _cur_xform[4], _cur_xform[5], _cur_xform[6] }
end
local function _pop_xform()
    local m = table.remove(_xform_stack)
    if m then _cur_xform = m end
end

function nvgCreate(_) return 1 end
function nvgDelete(_) end
function nvgCreateFont(_, _, _) return 1 end
function nvgBeginFrame(_, _, _, _) end
function nvgEndFrame(_) end

function nvgSave(_)
    _push_xform()
    __recorder.depth = __recorder.depth + 1
end
function nvgRestore(_)
    _pop_xform()
    __recorder.depth = math.max(0, __recorder.depth - 1)
end

function nvgTranslate(_, x, y)
    _cur_xform[5] = _cur_xform[5] + _cur_xform[1] * x + _cur_xform[3] * y
    _cur_xform[6] = _cur_xform[6] + _cur_xform[2] * x + _cur_xform[4] * y
end
function nvgScale(_, sx, sy)
    _cur_xform[1] = _cur_xform[1] * sx
    _cur_xform[2] = _cur_xform[2] * sx
    _cur_xform[3] = _cur_xform[3] * sy
    _cur_xform[4] = _cur_xform[4] * sy
end
function nvgRotate(_, _) end
function nvgResetTransform(_) _cur_xform = { 1, 0, 0, 1, 0, 0 } end

function nvgRGB(r, g, b) return { r = r, g = g, b = b, a = 255 } end
function nvgRGBA(r, g, b, a) return { r = r, g = g, b = b, a = a } end

function nvgFontFace(_, _) end
function nvgFontSize(_, _) end
function nvgFontFaceId(_, _) end
function nvgFillColor(_, _) end
function nvgStrokeColor(_, _) end
function nvgStrokeWidth(_, _) end
function nvgGlobalAlpha(_, _) end
function nvgTextAlign(_, _) end

-- NanoVG 标志位常量（按 NanoVG 头文件 nvg.h 定义）
NVG_ALIGN_LEFT     = 1
NVG_ALIGN_CENTER   = 2
NVG_ALIGN_RIGHT    = 4
NVG_ALIGN_TOP      = 8
NVG_ALIGN_MIDDLE   = 16
NVG_ALIGN_BOTTOM   = 32
NVG_ALIGN_BASELINE = 64
NVG_IMAGE_REPEATX  = 1
NVG_IMAGE_REPEATY  = 2
NVG_IMAGE_FLIPY    = 4
NVG_IMAGE_PREMULTIPLIED = 8
NVG_IMAGE_NEAREST  = 16
NVG_IMAGE_GENERATE_MIPMAPS = 32
NVG_IMAGE_NOFILTER = NVG_IMAGE_NEAREST
NVG_HOLE = 0
NVG_CCW  = 1
NVG_CW   = 2
NVG_BUTT = 0
NVG_ROUND = 1
NVG_SQUARE = 2
NVG_MITER = 0
NVG_BEVEL = 3

function nvgBeginPath(_) end
function nvgRect(_, _, _, _, _) end
function nvgRoundedRect(_, _, _, _, _, _) end
function nvgCircle(_, _, _, _) end
function nvgEllipse(_, _, _, _, _) end
function nvgMoveTo(_, _, _) end
function nvgLineTo(_, _, _) end
function nvgClosePath(_) end
function nvgFill(_) end
function nvgStroke(_) end
function nvgScissor(_, _, _, _, _) end
function nvgIntersectScissor(_, _, _, _, _) end
function nvgResetScissor(_) end

function nvgText(_, _, _, _) end
function nvgTextBox(_, _, _, _, _) end
function nvgTextBounds(_, _, _, _) return 0, { 0, 0, 0, 0 } end

-- 图像：返回递增 fake handle；nvgImageSize 假装 64×64（保证 D.Frames 等以为加载完）
-- 维护 handle → path 反查表，便于 nvgImagePattern 在事件中显示文件名
local _next_img = 1
local _handle_to_path = {}
function nvgCreateImage(_, path, _)
    local h = _next_img; _next_img = _next_img + 1
    if path then _handle_to_path[h] = tostring(path) end
    return h
end
function nvgDeleteImage(_, _) end
function nvgImageSize(_, _) return 64, 64 end
function nvgImagePattern(_, ox, oy, ew, eh, _, img, alpha)
    if __recorder and __recorder.enabled and ew and eh and ew > 0 and eh > 0 then
        local p = _handle_to_path[img] or ""
        -- 取末尾文件名（短一点显示）
        local short = p:match("([^/\\]+)$") or p
        rec({
            type = "DrawImage", api = "nvgImagePattern",
            x = ox, y = oy, w = ew, h = eh,
            src = caller_src(),
            hint = (short ~= "" and short) or ("img#"..tostring(img)),
        })
    end
    return { kind = "image", img = img, alpha = alpha }
end
function nvgFillPaint(_, _) end
function nvgStrokePaint(_, _) end
function nvgLinearGradient(_, _, _, _, _, _, _) return { kind = "linear" } end
function nvgBoxGradient(_, _, _, _, _, _, _, _, _) return { kind = "box" } end
function nvgRadialGradient(_, _, _, _, _, _, _) return { kind = "radial" } end

-- ---------- Renderer 拦截：在 require "Renderer" 之前 preload 一个 hook 版 ----------
-- 思路：先正常 require 真实 Renderer，再用 setmetatable 包装/或直接重定义其方法以追加 rec()
-- 这里采用"加载后 monkey-patch"方式，由 boot 入口 require 完 Renderer 后立即 patch。
local function patch_renderer(R)
    -- 包装表：每条方法在调用真实实现的同时记录矩形
    local function wrap(name, x_idx, y_idx, w_idx, h_idx, kind)
        local orig = R[name]
        if not orig then return end
        R[name] = function(...)
            local args = { ... }
            local ev = {
                type = kind or name,
                api  = name,
                x    = args[x_idx],
                y    = args[y_idx],
                w    = args[w_idx],
                h    = args[h_idx],
                src  = caller_src(),
            }
            rec(ev)
            return orig(...)
        end
    end

    -- 矩形类（参数顺序 x,y,w,h,...）
    wrap("FillRect",    1, 2, 3, 4, "FillRect")
    wrap("StrokeRect",  1, 2, 3, 4, "StrokeRect")
    wrap("FillRounded", 1, 2, 3, 4, "FillRounded")
    wrap("PixelPanel",  1, 2, 3, 4, "PixelPanel")
    wrap("GradRect",    1, 2, 3, 4, "GradRect")
    wrap("GradRectH",   1, 2, 3, 4, "GradRectH")
    wrap("HPBar",       1, 2, 3, 4, "HPBar")
    wrap("DrawImage",       2, 3, 4, 5, "DrawImage")     -- (handle,x,y,w,h,...)
    wrap("DrawImageRegion", 9,10,11,12, "DrawImageRegion") -- (h,iw,ih,sx,sy,sw,sh,dx,dy,dw,dh)
    wrap("DrawImageTiled",  2, 3, 4, 5, "DrawImageTiled")

    -- 圆/线类（特化）
    do
        local orig = R.FillCircle
        if orig then
            R.FillCircle = function(cx, cy, r, ...)
                rec({ type="FillCircle", api="FillCircle", x=cx-r, y=cy-r, w=r*2, h=r*2, src=caller_src() })
                return orig(cx, cy, r, ...)
            end
        end
    end
    do
        local orig = R.Line
        if orig then
            R.Line = function(x1, y1, x2, y2, ...)
                local minx, miny = math.min(x1, x2), math.min(y1, y2)
                rec({ type="Line", api="Line", x=minx, y=miny, w=math.abs(x2-x1), h=math.abs(y2-y1), src=caller_src() })
                return orig(x1, y1, x2, y2, ...)
            end
        end
    end

    -- 文本类（高度从 size 推；hint 取文本前 24 字符）
    local function wrap_text(name, align)
        local orig = R[name]
        if not orig then return end
        R[name] = function(txt, x, y, size, ...)
            local s = tostring(txt or "")
            rec({
                type = "Text", api = name, align = align,
                x = x, y = y - (size or 14), w = (#s) * (size or 14) * 0.55, h = size or 14,
                hint = s:sub(1, 24),
                src = caller_src(),
            })
            return orig(txt, x, y, size, ...)
        end
    end
    wrap_text("TextLeft",   "left")
    wrap_text("TextCenter", "center")
    wrap_text("TextRight",  "right")
    wrap_text("TextShadow", "shadow")

    return R
end

-- ---------- 入口 ----------
function __recorder.boot()
    -- 修改 package.path 由 JS 端做（在 dostring 之前已设置）
    -- 加载并 patch Renderer
    local R = require "Renderer"
    patch_renderer(R)
    __recorder._R = R

    -- 让所有图片"立即就绪"：替换 AssetLoader.IsReady / GetHandle / Request / Tick，
    -- 这样场景绘制不会因 AL.IsReady=false 而跳过 R.DrawImage。
    local ok, AL = pcall(require, "core.dispatcher.AssetLoader")
    if ok and AL then
        local fake_handles = {}
        local function handle_for(path)
            if not fake_handles[path] then
                local h = _next_img; _next_img = _next_img + 1
                _handle_to_path[h] = tostring(path)
                fake_handles[path] = h
            end
            return fake_handles[path]
        end
        AL.Request   = function(path, onReady, _) local h = handle_for(path); if onReady then pcall(onReady, h) end end
        AL.RequestBatch = function(list) for _, p in ipairs(list or {}) do handle_for(p) end end
        AL.GetHandle = function(path) return handle_for(path) end
        AL.IsReady   = function(_) return true end
        AL.Tick      = function() end
        AL.GetAspect = function(_) return 1.0 end
        AL.Status    = function() return { ready = 0, total = 0, queued = 0, loading = 0, failed = 0 } end
        __recorder._AL_patched = true
    end
end

function __recorder.reset()
    __recorder.events = {}
    __recorder.depth  = 0
end

function __recorder.set_enabled(v)
    __recorder.enabled = v and true or false
end

function __recorder.fire_render()
    local fn = __recorder.handlers["NanoVGRender"]
    if not fn then return false, "NanoVGRender handler not registered" end
    local f = _G[fn]
    if not f then return false, "no global "..fn end
    -- 模拟 Update：场景往往依赖 SM.Update 推动一次（让 Enter 内部计算也跑过）
    -- 这里只跑 Render，不跑 Update。
    local ok, err = pcall(f, "NanoVGRender", { GetFloat = function() return 0.016 end })
    if not ok then return false, tostring(err) end
    return true
end

return __recorder
