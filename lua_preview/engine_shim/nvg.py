"""NanoVG → pygame 适配层。

设计思路：
- nvgBeginPath 后续的 nvgRect/Rounded/Circle/MoveTo/LineTo/Ellipse/ClosePath
  都把"路径段"塞进 ctx 的 _path 缓冲；Fill/Stroke 时按当前矩阵
  + 当前色/Paint 一次性绘制到 ctx._target Surface。
- nvgSave / Restore 维护 (transform, scissor, fill_color, ...) 的栈。
- nvgTranslate/Scale/Rotate 直接乘到 transform 矩阵。
- 字体：用 pygame.font.Font 缓存 (ttf, size)。
- 图片：asset.py 提供 nvgCreateImage / nvgImageSize / nvgDeleteImage。
- nvgImagePattern / FillPaint：把 paint 信息存为字典；Fill 时按矩形把图片
  贴上去（计算 scale/offset）。线性/径向渐变同理：用 pygame 的 PixelArray
  逐像素混色太慢，简化为单中间色填充——作为"够看就行"的预览能接受。
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple
import math
import pygame


Mat = Tuple[float, float, float, float, float, float]  # a b c d e f (2x3)
IDENT: Mat = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mat_mul(m1: Mat, m2: Mat) -> Mat:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1*a2 + c1*b2,        b1*a2 + d1*b2,
        a1*c2 + c1*d2,        b1*c2 + d1*d2,
        a1*e2 + c1*f2 + e1,   b1*e2 + d1*f2 + f1,
    )


def mat_xform(m: Mat, x: float, y: float) -> Tuple[float, float]:
    a, b, c, d, e, f = m
    return a*x + c*y + e, b*x + d*y + f


@dataclass
class _State:
    xform: Mat = IDENT
    fill_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    stroke_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    stroke_width: float = 1.0
    fill_paint: Optional[dict] = None        # 当 paint 模式生效（覆盖 fill_color）
    font_face: str = "sans"
    font_size: float = 16.0
    text_align: int = 0
    composite: int = 0
    scissor: Optional[Tuple[float, float, float, float]] = None  # (x,y,w,h) in design


@dataclass
class NVGContext:
    target: pygame.Surface
    asset_loader: Any
    font_loader: Any
    state: _State = field(default_factory=_State)
    state_stack: List[_State] = field(default_factory=list)
    path: List[tuple] = field(default_factory=list)


# ===== 全局上下文表（lupa 拿到的句柄是普通 int，我们映射回 NVGContext）=====
_contexts: dict = {}
_next_handle = 1


def nvg_create_context(target: pygame.Surface, asset_loader, font_loader) -> int:
    global _next_handle
    h = _next_handle
    _next_handle += 1
    _contexts[h] = NVGContext(target=target, asset_loader=asset_loader, font_loader=font_loader)
    return h


def _ctx(vg) -> NVGContext:
    return _contexts[int(vg)]


# ─── 颜色工具 ────────────────────────────────────────
# 返回 list（不是 tuple）以避开 lupa 的 unpack_returned_tuples=True 拆包
def nvgRGB(r, g, b):       return [int(r), int(g), int(b), 255]
def nvgRGBA(r, g, b, a):   return [int(r), int(g), int(b), int(a)]


# ─── 帧 & 矩阵 ───────────────────────────────────────
def nvgBeginFrame(vg, w, h, dpr):
    c = _ctx(vg)
    c.state = _State()
    c.state_stack.clear()
    c.path.clear()


def nvgEndFrame(vg):
    pass


def nvgSave(vg):
    c = _ctx(vg)
    c.state_stack.append(_clone_state(c.state))


def nvgRestore(vg):
    c = _ctx(vg)
    if c.state_stack:
        c.state = c.state_stack.pop()


def _clone_state(s: _State) -> _State:
    return _State(
        xform=s.xform, fill_color=s.fill_color, stroke_color=s.stroke_color,
        stroke_width=s.stroke_width, fill_paint=s.fill_paint,
        font_face=s.font_face, font_size=s.font_size, text_align=s.text_align,
        composite=s.composite, scissor=s.scissor,
    )


def nvgTranslate(vg, x, y):
    c = _ctx(vg)
    c.state.xform = mat_mul(c.state.xform, (1, 0, 0, 1, x, y))


def nvgScale(vg, sx, sy):
    c = _ctx(vg)
    c.state.xform = mat_mul(c.state.xform, (sx, 0, 0, sy, 0, 0))


def nvgRotate(vg, ang):
    c = _ctx(vg)
    cs, sn = math.cos(ang), math.sin(ang)
    c.state.xform = mat_mul(c.state.xform, (cs, sn, -sn, cs, 0, 0))


def nvgScissor(vg, x, y, w, h):
    _ctx(vg).state.scissor = (x, y, w, h)


def nvgResetScissor(vg):
    _ctx(vg).state.scissor = None


def nvgGlobalCompositeOperation(vg, op):
    _ctx(vg).state.composite = op


# ─── 路径构造 ───────────────────────────────────────
def nvgBeginPath(vg):
    _ctx(vg).path.clear()


def nvgRect(vg, x, y, w, h):
    _ctx(vg).path.append(("rect", x, y, w, h))


def nvgRoundedRect(vg, x, y, w, h, r):
    _ctx(vg).path.append(("rrect", x, y, w, h, r))


def nvgCircle(vg, cx, cy, r):
    _ctx(vg).path.append(("circle", cx, cy, r))


def nvgEllipse(vg, cx, cy, rx, ry):
    _ctx(vg).path.append(("ellipse", cx, cy, rx, ry))


def nvgMoveTo(vg, x, y):
    _ctx(vg).path.append(("move", x, y))


def nvgLineTo(vg, x, y):
    _ctx(vg).path.append(("line", x, y))


def nvgClosePath(vg):
    _ctx(vg).path.append(("close",))


# ─── Paint ───────────────────────────────────────
def nvgFillColor(vg, col):
    c = _ctx(vg)
    c.state.fill_color = col
    c.state.fill_paint = None


def nvgStrokeColor(vg, col):
    _ctx(vg).state.stroke_color = col


def nvgStrokeWidth(vg, w):
    _ctx(vg).state.stroke_width = w


def nvgLinearGradient(vg, sx, sy, ex, ey, col1, col2):
    return {"kind": "linear", "sx": sx, "sy": sy, "ex": ex, "ey": ey, "c1": col1, "c2": col2}


def nvgRadialGradient(vg, cx, cy, inr, outr, col1, col2):
    return {"kind": "radial", "cx": cx, "cy": cy, "inr": inr, "outr": outr, "c1": col1, "c2": col2}


def nvgImagePattern(vg, ox, oy, ew, eh, ang, img, alpha):
    return {"kind": "image", "ox": ox, "oy": oy, "ew": ew, "eh": eh,
            "ang": ang, "img": int(img), "alpha": alpha}


def nvgFillPaint(vg, paint):
    _ctx(vg).state.fill_paint = paint


# ─── 字体 ───────────────────────────────────────
def nvgCreateFont(vg, name, path):
    return _ctx(vg).font_loader.register(name, path)


def nvgFontFace(vg, name):
    _ctx(vg).state.font_face = name


def nvgFontSize(vg, size):
    _ctx(vg).state.font_size = size


def nvgTextAlign(vg, flags):
    _ctx(vg).state.text_align = int(flags)


# ─── 图片 ───────────────────────────────────────
def nvgCreateImage(vg, path, _flags):
    return _ctx(vg).asset_loader.create_image(path)


def nvgImageSize(vg, h):
    return _ctx(vg).asset_loader.image_size(int(h))


def nvgDeleteImage(vg, h):
    _ctx(vg).asset_loader.delete_image(int(h))


def nvgDelete(vg):
    _contexts.pop(int(vg), None)


def nvgCreate(_flags):
    # 此函数返回的是上层 main.lua 调的 vg 句柄；
    # 真实创建在 run.py 启动时已完成，这里只返回当前唯一 ctx 句柄。
    return next(iter(_contexts.keys()))


# ─── 实际绘制：Fill / Stroke / Text ────────────────
def _apply_clip(c: NVGContext) -> Tuple[pygame.Surface, Tuple[int, int]]:
    """如有 scissor，返回 (sub_surface, offset)。否则 (target, (0,0))。"""
    sc = c.state.scissor
    if not sc:
        return c.target, (0, 0)
    x, y, w, h = sc
    (x1, y1) = mat_xform(c.state.xform, x, y)
    (x2, y2) = mat_xform(c.state.xform, x + w, y + h)
    rx, ry = int(min(x1, x2)), int(min(y1, y2))
    rw, rh = int(abs(x2 - x1)), int(abs(y2 - y1))
    rect = pygame.Rect(rx, ry, rw, rh).clip(c.target.get_rect())
    if rect.w <= 0 or rect.h <= 0:
        return None, (0, 0)
    return c.target.subsurface(rect), (rect.x, rect.y)


def _xform_rect(c: NVGContext, x, y, w, h):
    """简化：只支持平移+均匀缩放（游戏用法符合）。"""
    (x1, y1) = mat_xform(c.state.xform, x, y)
    (x2, y2) = mat_xform(c.state.xform, x + w, y + h)
    return int(round(min(x1, x2))), int(round(min(y1, y2))), \
           int(round(abs(x2 - x1))), int(round(abs(y2 - y1)))


def _xform_pt(c: NVGContext, x, y):
    px, py = mat_xform(c.state.xform, x, y)
    return int(round(px)), int(round(py))


def _xform_scale(c: NVGContext) -> float:
    a, b, _c, d, _e, _f = c.state.xform
    return math.sqrt(abs(a * d - b * _c))


def _resolve_fill_color(c: NVGContext, x, y, w, h):
    p = c.state.fill_paint
    if not p:
        return c.state.fill_color
    if p["kind"] == "linear":
        # 简化：取中间色
        c1, c2 = p["c1"], p["c2"]
        return tuple((c1[i] + c2[i]) // 2 for i in range(4))
    if p["kind"] == "radial":
        c1, c2 = p["c1"], p["c2"]
        return tuple((c1[i] + c2[i]) // 2 for i in range(4))
    return c.state.fill_color


def _draw_image_paint(c: NVGContext, paint, dst_rect):
    img = c.asset_loader.get_surface(paint["img"])
    if img is None:
        return
    # paint 把整张图投影到 (ox, oy, ox+ew, oy+eh) 这个设计坐标矩形
    ox, oy, ew, eh = paint["ox"], paint["oy"], paint["ew"], paint["eh"]
    dx, dy, dw, dh = dst_rect
    if ew <= 0 or eh <= 0 or dw <= 0 or dh <= 0:
        return
    # 缩放后整图大小（屏幕像素）
    s = _xform_scale(c)
    full_w = max(1, int(round(ew * s)))
    full_h = max(1, int(round(eh * s)))
    try:
        scaled = pygame.transform.smoothscale(img, (full_w, full_h)) if img.get_bitsize() >= 24 else pygame.transform.scale(img, (full_w, full_h))
    except Exception:
        scaled = pygame.transform.scale(img, (full_w, full_h))
    # 处理翻转：transform 的 a/d 分量为负则对应轴需要翻转
    a, b, cc, d, _, _ = c.state.xform
    flip_x = a < 0
    flip_y = d < 0
    if flip_x or flip_y:
        scaled = pygame.transform.flip(scaled, flip_x, flip_y)
    alpha = max(0.0, min(1.0, paint.get("alpha", 1.0)))
    if alpha < 1.0:
        scaled = scaled.copy()
        scaled.set_alpha(int(alpha * 255))
    # 整图左上角的屏幕坐标（取四角包围盒的左上）
    x1, y1 = mat_xform(c.state.xform, ox, oy)
    x2, y2 = mat_xform(c.state.xform, ox + ew, oy + eh)
    img_screen_x = int(round(min(x1, x2)))
    img_screen_y = int(round(min(y1, y2)))
    # 用 dst_rect 做 blit 区域裁剪（src 区域 = dst 在大图中对应的偏移）
    src_x = dx - img_screen_x
    src_y = dy - img_screen_y
    src_rect = pygame.Rect(src_x, src_y, dw, dh).clip(scaled.get_rect())
    if src_rect.w <= 0 or src_rect.h <= 0:
        return
    surf, off = _apply_clip(c)
    if surf is None:
        return
    surf.blit(scaled, (dx - off[0] + (src_rect.x - src_x),
                       dy - off[1] + (src_rect.y - src_y)),
              area=src_rect)


def _draw_image_paint_polygon(c, paint, xpts_screen, dst_surf, off):
    """多边形（屏幕坐标）+ image paint：把 paint 描述的整图投到 (ox,oy,ew,eh) 内，
    再用多边形蒙板裁剪。xpts_screen 已经是 dst_surf 局部坐标。"""
    img = c.asset_loader.get_surface(paint["img"])
    if img is None:
        return
    ox, oy, ew, eh = paint["ox"], paint["oy"], paint["ew"], paint["eh"]
    if ew <= 0 or eh <= 0 or not xpts_screen:
        return
    s = _xform_scale(c)
    full_w = max(1, int(round(ew * s)))
    full_h = max(1, int(round(eh * s)))
    try:
        scaled = pygame.transform.smoothscale(img, (full_w, full_h)) if img.get_bitsize() >= 24 else pygame.transform.scale(img, (full_w, full_h))
    except Exception:
        scaled = pygame.transform.scale(img, (full_w, full_h))
    alpha = max(0.0, min(1.0, paint.get("alpha", 1.0)))
    if alpha < 1.0:
        scaled = scaled.copy(); scaled.set_alpha(int(alpha * 255))
    img_screen_x, img_screen_y = mat_xform(c.state.xform, ox, oy)
    img_screen_x = int(round(img_screen_x)) - off[0]
    img_screen_y = int(round(img_screen_y)) - off[1]
    # 多边形 bbox（dst_surf 局部）
    xs = [p[0] for p in xpts_screen]; ys = [p[1] for p in xpts_screen]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    bw, bh = maxx - minx, maxy - miny
    if bw <= 0 or bh <= 0:
        return
    # 临时蒙板：先画多边形再 blit 缩放后的整图
    tmp = pygame.Surface((bw, bh), pygame.SRCALPHA)
    poly_local = [(p[0] - minx, p[1] - miny) for p in xpts_screen]
    pygame.draw.polygon(tmp, (255, 255, 255, 255), poly_local)
    # 把 scaled 图按 (img_screen_x - minx, img_screen_y - miny) 偏移贴到 tmp，并保留 tmp 的 alpha 蒙板
    img_layer = pygame.Surface((bw, bh), pygame.SRCALPHA)
    img_layer.blit(scaled, (img_screen_x - minx, img_screen_y - miny))
    img_layer.blit(tmp, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst_surf.blit(img_layer, (minx, miny))


def nvgFill(vg):
    c = _ctx(vg)
    surf, off = _apply_clip(c)
    if surf is None:
        return
    paint = c.state.fill_paint
    # 收集本次 path 中可绘制的几何体
    polys, rects, rrects, circles, ellipses = _collect_shapes(c)
    for shape in rects:
        x, y, w, h = _xform_rect(c, *shape)
        if w <= 0 or h <= 0:
            continue
        if paint and paint.get("kind") == "image":
            _draw_image_paint(c, paint, (x, y, w, h))
        else:
            col = _resolve_fill_color(c, *shape)
            _fill_rect(surf, off, x, y, w, h, col)
    for x, y, w, h, r in rrects:
        rx, ry, rw, rh = _xform_rect(c, x, y, w, h)
        if rw <= 0 or rh <= 0:
            continue
        col = _resolve_fill_color(c, x, y, w, h)
        rr = max(0, int(round(r * _xform_scale(c))))
        rect = pygame.Rect(rx - off[0], ry - off[1], rw, rh)
        try:
            pygame.draw.rect(surf, col, rect, border_radius=rr)
        except TypeError:
            pygame.draw.rect(surf, col, rect)
    for cx, cy, r in circles:
        px, py = _xform_pt(c, cx, cy)
        rr = max(1, int(round(r * _xform_scale(c))))
        pygame.draw.circle(surf, _resolve_fill_color(c, cx - r, cy - r, r * 2, r * 2),
                           (px - off[0], py - off[1]), rr)
    for cx, cy, rx, ry in ellipses:
        s = _xform_scale(c)
        bx, by = _xform_pt(c, cx - rx, cy - ry)
        bw, bh = int(round(rx * 2 * s)), int(round(ry * 2 * s))
        if bw > 0 and bh > 0:
            pygame.draw.ellipse(surf, _resolve_fill_color(c, cx - rx, cy - ry, rx * 2, ry * 2),
                                pygame.Rect(bx - off[0], by - off[1], bw, bh))
    for poly in polys:
        if len(poly) >= 3:
            xpts = [(int(round(px)) - off[0], int(round(py)) - off[1])
                    for (px, py) in (mat_xform(c.state.xform, x, y) for (x, y) in poly)]
            if paint and paint.get("kind") == "image":
                # 多边形 + image paint：用临时 surface 做多边形蒙板裁剪
                _draw_image_paint_polygon(c, paint, xpts, surf, off)
            else:
                col = _resolve_fill_color(c, 0, 0, 1, 1)
                pygame.draw.polygon(surf, col, xpts)


def nvgStroke(vg):
    c = _ctx(vg)
    surf, off = _apply_clip(c)
    if surf is None:
        return
    polys, rects, rrects, circles, ellipses = _collect_shapes(c)
    sw = max(1, int(round(c.state.stroke_width * _xform_scale(c))))
    col = c.state.stroke_color
    for shape in rects:
        x, y, w, h = _xform_rect(c, *shape)
        pygame.draw.rect(surf, col, pygame.Rect(x - off[0], y - off[1], w, h), sw)
    for x, y, w, h, r in rrects:
        rx, ry, rw, rh = _xform_rect(c, x, y, w, h)
        rr = max(0, int(round(r * _xform_scale(c))))
        try:
            pygame.draw.rect(surf, col, pygame.Rect(rx - off[0], ry - off[1], rw, rh),
                             sw, border_radius=rr)
        except TypeError:
            pygame.draw.rect(surf, col, pygame.Rect(rx - off[0], ry - off[1], rw, rh), sw)
    for cx, cy, r in circles:
        px, py = _xform_pt(c, cx, cy)
        pygame.draw.circle(surf, col, (px - off[0], py - off[1]),
                           max(1, int(round(r * _xform_scale(c)))), sw)
    for poly in polys:
        if len(poly) >= 2:
            pts = [(int(round(px)) - off[0], int(round(py)) - off[1])
                   for (px, py) in (mat_xform(c.state.xform, x, y) for (x, y) in poly)]
            pygame.draw.lines(surf, col, False, pts, sw)


def _collect_shapes(c: NVGContext):
    polys: List[List[Tuple[float, float]]] = []
    rects, rrects, circles, ellipses = [], [], [], []
    cur: List[Tuple[float, float]] = []
    for op in c.path:
        if op[0] == "rect":
            rects.append(op[1:])
        elif op[0] == "rrect":
            rrects.append(op[1:])
        elif op[0] == "circle":
            circles.append(op[1:])
        elif op[0] == "ellipse":
            ellipses.append(op[1:])
        elif op[0] == "move":
            if cur:
                polys.append(cur)
            cur = [(op[1], op[2])]
        elif op[0] == "line":
            cur.append((op[1], op[2]))
        elif op[0] == "close":
            if cur:
                polys.append(cur)
                cur = []
    if cur:
        polys.append(cur)
    return polys, rects, rrects, circles, ellipses


def _fill_rect(surf, off, x, y, w, h, col):
    if len(col) == 4 and col[3] < 255:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill(col)
        surf.blit(s, (x - off[0], y - off[1]))
    else:
        surf.fill(col[:3], pygame.Rect(x - off[0], y - off[1], w, h))


# ─── 文字 ───────────────────────────────────────
def nvgText(vg, x, y, txt):
    c = _ctx(vg)
    surf, off = _apply_clip(c)
    if surf is None or txt is None:
        return
    txt = str(txt)
    s = _xform_scale(c)
    px_size = max(8, int(round(c.state.font_size * s)))
    font = c.font_loader.get(c.state.font_face, px_size)
    if not font:
        return
    color = c.state.fill_color
    img = font.render(txt, True, color[:3])
    if len(color) == 4 and color[3] < 255:
        img.set_alpha(color[3])
    tw, th = img.get_size()
    px, py = mat_xform(c.state.xform, x, y)
    a = c.state.text_align
    if a & NVG_ALIGN_CENTER_BIT:
        px -= tw / 2
    elif a & NVG_ALIGN_RIGHT_BIT:
        px -= tw
    if a & NVG_ALIGN_MIDDLE_BIT:
        py -= th / 2
    elif a & NVG_ALIGN_BOTTOM_BIT:
        py -= th
    elif a & NVG_ALIGN_BASELINE_BIT:
        py -= font.get_ascent()
    surf.blit(img, (int(round(px)) - off[0], int(round(py)) - off[1]))


# 对齐位（与 constants.py 同步）
NVG_ALIGN_LEFT_BIT     = 1 << 0
NVG_ALIGN_CENTER_BIT   = 1 << 1
NVG_ALIGN_RIGHT_BIT    = 1 << 2
NVG_ALIGN_TOP_BIT      = 1 << 3
NVG_ALIGN_MIDDLE_BIT   = 1 << 4
NVG_ALIGN_BOTTOM_BIT   = 1 << 5
NVG_ALIGN_BASELINE_BIT = 1 << 6


def install(lua):
    """把所有 nvg* 函数塞进 Lua 全局。"""
    g = lua.globals()
    for name, val in globals().items():
        if name.startswith("nvg") and callable(val):
            g[name] = val
