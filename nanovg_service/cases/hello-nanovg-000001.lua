-- 示例：渐变背景 + 圆角面板 + 居中文字 + 装饰圆环
-- 全局可用：vg, WIDTH, HEIGHT, DPR, ASSETS_DIR
nvgFontFace(vg, "default")

-- 背景渐变
local bg = nvgLinearGradient(vg, 0, 0, 0, HEIGHT,
  nvgRGB(40, 60, 100), nvgRGB(15, 20, 40))
nvgBeginPath(vg); nvgRect(vg, 0, 0, WIDTH, HEIGHT)
nvgFillPaint(vg, bg); nvgFill(vg)

-- 中央面板
local px, py, pw, ph = 60, 60, WIDTH-120, HEIGHT-120
nvgBeginPath(vg); nvgRoundedRect(vg, px, py, pw, ph, 20)
nvgFillColor(vg, nvgRGBA(255,255,255,18)); nvgFill(vg)
nvgStrokeColor(vg, nvgRGBA(255,255,255,160)); nvgStrokeWidth(vg, 2); nvgStroke(vg)

-- 装饰圆环
for i = 0, 3 do
  nvgBeginPath(vg)
  nvgCircle(vg, px + pw - 50 - i*22, py + 50, 8)
  nvgFillColor(vg, nvgHSLA(i/4, 0.8, 0.6, 220))
  nvgFill(vg)
end

-- 标题
nvgFontSize(vg, 36)
nvgFillColor(vg, nvgRGB(255,255,255))
nvgTextAlign(vg, NVG_ALIGN_CENTER + NVG_ALIGN_MIDDLE)
nvgText(vg, WIDTH/2, HEIGHT/2 - 10, "Hello NanoVG")

-- 副标题
nvgFontSize(vg, 14)
nvgFillColor(vg, nvgRGBA(255,255,255,180))
nvgText(vg, WIDTH/2, HEIGHT/2 + 24, "from Lua, rendered headless")
