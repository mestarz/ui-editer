"""NanoVG → librender (cffi) backend for lua_preview.

Goal
----
Replace the pygame-based pseudo-nanovg in ``nvg.py`` with calls to a real
nanovg context running on OSMesa (software OpenGL) inside librender.so.
The result is bit-for-bit comparable to TapTap's nanovg output, eliminating
gradient/scissor/AA discrepancies.

Usage
-----
The public surface mirrors ``nvg.py`` exactly:

    nvg_create_context(target_surface, asset_loader, font_loader) -> int
    install(lua)            # registers nvg* / NVG_* into Lua globals
    blit_to_surface(vg, target_surface)   # called once per frame after EndFrame

Everything in between (Begin/EndFrame, paths, fills, ...) is dispatched
from Lua and ends up in librender via cffi.
"""
from __future__ import annotations
import os
import pathlib
from typing import Any, Optional, Tuple

import cffi
import pygame

# ---------------------------------------------------------------------------
#  cffi binding
# ---------------------------------------------------------------------------
_ffi = cffi.FFI()
_ffi.cdef(
    """
    typedef struct ctx ctx;
    ctx *nvgr_init(int w, int h, float dpr);
    int  nvgr_resize(ctx *c, int w, int h, float dpr);
    void nvgr_destroy(ctx *c);
    const uint8_t *nvgr_pixels(ctx *c);
    int nvgr_fb_width(ctx *c);
    int nvgr_fb_height(ctx *c);

    void nvgr_begin_frame(ctx *c);
    void nvgr_end_frame(ctx *c);
    void nvgr_cancel_frame(ctx *c);

    void nvgr_save(ctx *c);
    void nvgr_restore(ctx *c);
    void nvgr_reset(ctx *c);
    void nvgr_translate(ctx *c, float x, float y);
    void nvgr_scale(ctx *c, float sx, float sy);
    void nvgr_rotate(ctx *c, float a);
    void nvgr_skew_x(ctx *c, float a);
    void nvgr_skew_y(ctx *c, float a);
    void nvgr_reset_transform(ctx *c);
    void nvgr_global_alpha(ctx *c, float a);
    void nvgr_global_composite_op(ctx *c, int op);

    void nvgr_scissor(ctx *c, float x, float y, float w, float h);
    void nvgr_intersect_scissor(ctx *c, float x, float y, float w, float h);
    void nvgr_reset_scissor(ctx *c);

    void nvgr_begin_path(ctx *c);
    void nvgr_close_path(ctx *c);
    void nvgr_path_winding(ctx *c, int dir);
    void nvgr_move_to(ctx *c, float x, float y);
    void nvgr_line_to(ctx *c, float x, float y);
    void nvgr_bezier_to(ctx *c, float c1x, float c1y, float c2x, float c2y, float x, float y);
    void nvgr_quad_to(ctx *c, float cx, float cy, float x, float y);
    void nvgr_arc_to(ctx *c, float x1, float y1, float x2, float y2, float r);
    void nvgr_arc(ctx *c, float cx, float cy, float r, float a0, float a1, int dir);
    void nvgr_rect(ctx *c, float x, float y, float w, float h);
    void nvgr_rounded_rect(ctx *c, float x, float y, float w, float h, float r);
    void nvgr_rounded_rect_varying(ctx *c, float x, float y, float w, float h,
                                   float rTL, float rTR, float rBR, float rBL);
    void nvgr_ellipse(ctx *c, float cx, float cy, float rx, float ry);
    void nvgr_circle(ctx *c, float cx, float cy, float r);

    void nvgr_fill_color(ctx *c, uint8_t r, uint8_t g, uint8_t b, uint8_t a);
    void nvgr_stroke_color(ctx *c, uint8_t r, uint8_t g, uint8_t b, uint8_t a);
    void nvgr_stroke_width(ctx *c, float w);
    void nvgr_miter_limit(ctx *c, float l);
    void nvgr_line_cap(ctx *c, int cap);
    void nvgr_line_join(ctx *c, int j);
    void nvgr_fill(ctx *c);
    void nvgr_stroke(ctx *c);

    int nvgr_linear_gradient(ctx *c, float sx, float sy, float ex, float ey,
        uint8_t r1, uint8_t g1, uint8_t b1, uint8_t a1,
        uint8_t r2, uint8_t g2, uint8_t b2, uint8_t a2);
    int nvgr_radial_gradient(ctx *c, float cx, float cy, float inr, float outr,
        uint8_t r1, uint8_t g1, uint8_t b1, uint8_t a1,
        uint8_t r2, uint8_t g2, uint8_t b2, uint8_t a2);
    int nvgr_box_gradient(ctx *c, float x, float y, float w, float h, float r, float f,
        uint8_t r1, uint8_t g1, uint8_t b1, uint8_t a1,
        uint8_t r2, uint8_t g2, uint8_t b2, uint8_t a2);
    int nvgr_image_pattern(ctx *c, float ox, float oy, float ew, float eh, float angle,
                           int image, float alpha);
    void nvgr_fill_paint(ctx *c, int paint_id);
    void nvgr_stroke_paint(ctx *c, int paint_id);

    int  nvgr_create_font(ctx *c, const char *name, const char *path);
    int  nvgr_find_font(ctx *c, const char *name);
    int  nvgr_add_fallback_font(ctx *c, const char *base_name, const char *fallback_name);
    void nvgr_font_face(ctx *c, const char *name);
    void nvgr_font_face_id(ctx *c, int font_id);
    void nvgr_font_size(ctx *c, float size);
    void nvgr_font_blur(ctx *c, float b);
    void nvgr_text_align(ctx *c, int align);
    void nvgr_text_letter_spacing(ctx *c, float s);
    void nvgr_text_line_height(ctx *c, float h);
    float nvgr_text(ctx *c, float x, float y, const char *s, int len);
    void  nvgr_text_box(ctx *c, float x, float y, float break_w, const char *s, int len);
    float nvgr_text_bounds(ctx *c, float x, float y, const char *s, int len, float bounds[4]);
    void  nvgr_text_box_bounds(ctx *c, float x, float y, float break_w, const char *s, int len, float bounds[4]);
    void  nvgr_text_metrics(ctx *c, float *ascender, float *descender, float *lineh);

    int  nvgr_create_image(ctx *c, const char *path, int flags);
    int  nvgr_create_image_mem(ctx *c, int flags, const uint8_t *data, int n);
    int  nvgr_create_image_rgba(ctx *c, int w, int h, int flags, const uint8_t *data);
    void nvgr_update_image(ctx *c, int image, const uint8_t *data);
    void nvgr_image_size(ctx *c, int image, int *w, int *h);
    void nvgr_delete_image(ctx *c, int image);

    void nvgr_current_transform(ctx *c, float xform[6]);
    float nvgr_deg_to_rad(float deg);
    float nvgr_rad_to_deg(float rad);
    """
)


def _load_lib() -> Any:
    here = pathlib.Path(__file__).resolve().parent
    candidates = [
        here.parent / "librender" / "build" / "libnvgrender.so",
        here.parent / "librender" / "libnvgrender.so",
    ]
    env = os.environ.get("LUA_PREVIEW_LIBRENDER")
    if env:
        candidates.insert(0, pathlib.Path(env))
    # 在 conda 等自带较旧 libstdc++ 的 Python 中，OSMesa→LLVM 链上需要的
    # GLIBCXX_3.4.30 找不到，会导致 dlopen 失败。这里显式 preload 系统的
    # libstdc++.so.6（通常是较新的 13/14 ABI），让其符号优先满足。
    for sysstdcpp in (
        "/lib/x86_64-linux-gnu/libstdc++.so.6",
        "/usr/lib/x86_64-linux-gnu/libstdc++.so.6",
    ):
        if os.path.exists(sysstdcpp):
            try:
                import ctypes
                ctypes.CDLL(sysstdcpp, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
            break
    for p in candidates:
        if p.exists():
            return _ffi.dlopen(str(p))
    raise FileNotFoundError(
        f"libnvgrender.so not found. Build it: cd {here.parent}/librender && ./build.sh"
    )


_lib = _load_lib()


# ---------------------------------------------------------------------------
#  Context
# ---------------------------------------------------------------------------
# Each lua_preview process has a single nanovg context; we still keep a handle
# table so the public API ``nvg_create_context`` matches the old shim signature.
_contexts: dict = {}
_next_handle = 1


class _NativeCtx:
    """Owns one librender context and the associated pygame surface."""

    def __init__(self, target: pygame.Surface, asset_loader, font_loader):
        self.target = target
        self.asset_loader = asset_loader  # kept for parity / image loading hooks
        self.font_loader = font_loader    # not used for rendering anymore
        w, h = target.get_size()
        self.win_w, self.win_h = int(w), int(h)
        self.dpr = 1.0
        self._c = _lib.nvgr_init(self.win_w, self.win_h, self.dpr)
        if not self._c:
            raise RuntimeError("nvgr_init failed (OSMesa context creation)")
        # The image cache from asset_loader is now bypassed; we register
        # nanovg images on first use, keyed by absolute path.
        self._image_handles: dict[str, int] = {}
        # Track Lua-visible handles per font name for diagnostics.
        self._fonts: dict[str, int] = {}

    def close(self):
        if self._c:
            _lib.nvgr_destroy(self._c)
            self._c = _ffi.NULL

    def resize_if_needed(self):
        w, h = self.target.get_size()
        if w != self.win_w or h != self.win_h:
            self.win_w, self.win_h = int(w), int(h)
            _lib.nvgr_resize(self._c, self.win_w, self.win_h, self.dpr)

    @property
    def c(self):
        return self._c


def _ctx(vg) -> _NativeCtx:
    return _contexts[int(vg)]


def nvg_create_context(target: pygame.Surface, asset_loader, font_loader) -> int:
    """Create a new nanovg context bound to a pygame target surface."""
    global _next_handle
    h = _next_handle
    _next_handle += 1
    _contexts[h] = _NativeCtx(target, asset_loader, font_loader)
    return h


def blit_to_surface(vg: int, target: Optional[pygame.Surface] = None) -> None:
    """Copy the librender RGBA framebuffer into ``target`` (defaults to ctx.target).

    Call this once per frame, AFTER nvgEndFrame.
    """
    c = _ctx(vg)
    surf = target or c.target
    fb_w = _lib.nvgr_fb_width(c.c)
    fb_h = _lib.nvgr_fb_height(c.c)
    n = fb_w * fb_h * 4
    raw = _ffi.buffer(_lib.nvgr_pixels(c.c), n)
    img = pygame.image.frombuffer(bytes(raw), (fb_w, fb_h), "RGBA")
    if (fb_w, fb_h) != surf.get_size():
        img = pygame.transform.smoothscale(img, surf.get_size())
    surf.blit(img, (0, 0))


# ---------------------------------------------------------------------------
#  Color helpers (tables match old shim format: list of 4 ints)
# ---------------------------------------------------------------------------
def nvgRGB(r, g, b):       return [int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF, 255]
def nvgRGBA(r, g, b, a):   return [int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF, int(a) & 0xFF]
def nvgRGBf(r, g, b):      return [int(r * 255), int(g * 255), int(b * 255), 255]
def nvgRGBAf(r, g, b, a):  return [int(r * 255), int(g * 255), int(b * 255), int(a * 255)]
def nvgTransRGBA(col, a):  return [col[0], col[1], col[2], int(a) & 0xFF]
def nvgTransRGBAf(col, a): return [col[0], col[1], col[2], int(a * 255) & 0xFF]


def _hsl_to_rgb(h, s, l):
    h = h - int(h)
    if s == 0:
        v = int(l * 255)
        return v, v, v
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    def hue(t):
        if t < 0: t += 1
        if t > 1: t -= 1
        if t < 1/6: return p + (q - p) * 6 * t
        if t < 1/2: return q
        if t < 2/3: return p + (q - p) * (2/3 - t) * 6
        return p
    return int(hue(h + 1/3) * 255), int(hue(h) * 255), int(hue(h - 1/3) * 255)


def nvgHSL(h, s, l):       r,g,b = _hsl_to_rgb(h, s, l); return [r, g, b, 255]
def nvgHSLA(h, s, l, a):   r,g,b = _hsl_to_rgb(h, s, l); return [r, g, b, int(a) & 0xFF]


def nvgLerpRGBA(c0, c1, u):
    u = max(0.0, min(1.0, float(u)))
    return [int(c0[i] * (1 - u) + c1[i] * u) for i in range(4)]


def _col(col):
    """Coerce a color (Python list/tuple [r,g,b,a] OR Lua 1-indexed table) into 4 uint8 channels."""
    if col is None:
        return 255, 255, 255, 255
    # Python list/tuple is the common case (our nvgRGB/nvgRGBA returns lists, and
    # Lua → Python via lupa keeps these as lists). Lua-side tables created with
    # ``{r,g,b,a}`` arrive as ``lupa._lupa._LuaTable`` which is 1-indexed, so we
    # detect that by absence of __getitem__[0].
    if isinstance(col, (list, tuple)):
        r = int(col[0]) & 0xFF
        g = int(col[1]) & 0xFF
        b = int(col[2]) & 0xFF
        a = int(col[3]) & 0xFF if len(col) > 3 else 255
        return r, g, b, a
    # Lua table path
    try:
        r = int(col[1]) & 0xFF
        g = int(col[2]) & 0xFF
        b = int(col[3]) & 0xFF
        try:    a = int(col[4]) & 0xFF
        except Exception: a = 255
        return r, g, b, a
    except Exception:
        pass
    # Last-resort 0-indexed access for unknown sequence types
    try:
        return int(col[0]) & 0xFF, int(col[1]) & 0xFF, int(col[2]) & 0xFF, (int(col[3]) & 0xFF if len(col) > 3 else 255)
    except Exception:
        return 255, 255, 255, 255


# ---------------------------------------------------------------------------
#  Frame
# ---------------------------------------------------------------------------
def nvgBeginFrame(vg, w, h, dpr):
    c = _ctx(vg)
    c.dpr = float(dpr) if dpr else 1.0
    c.resize_if_needed()
    _lib.nvgr_begin_frame(c.c)

def nvgEndFrame(vg):
    c = _ctx(vg)
    _lib.nvgr_end_frame(c.c)
    # Auto-blit so legacy callers that don't know about blit_to_surface
    # still see something on screen. Cheap (~2ms at 1280x720).
    blit_to_surface(vg)

def nvgCancelFrame(vg): _lib.nvgr_cancel_frame(_ctx(vg).c)


# ---------------------------------------------------------------------------
#  State / transforms
# ---------------------------------------------------------------------------
def nvgSave(vg):                _lib.nvgr_save(_ctx(vg).c)
def nvgRestore(vg):             _lib.nvgr_restore(_ctx(vg).c)
def nvgReset(vg):               _lib.nvgr_reset(_ctx(vg).c)
def nvgTranslate(vg, x, y):     _lib.nvgr_translate(_ctx(vg).c, x, y)
def nvgScale(vg, sx, sy):       _lib.nvgr_scale(_ctx(vg).c, sx, sy)
def nvgRotate(vg, ang):         _lib.nvgr_rotate(_ctx(vg).c, ang)
def nvgSkewX(vg, ang):          _lib.nvgr_skew_x(_ctx(vg).c, ang)
def nvgSkewY(vg, ang):          _lib.nvgr_skew_y(_ctx(vg).c, ang)
def nvgResetTransform(vg):      _lib.nvgr_reset_transform(_ctx(vg).c)
def nvgGlobalAlpha(vg, a):      _lib.nvgr_global_alpha(_ctx(vg).c, a)
def nvgGlobalCompositeOperation(vg, op): _lib.nvgr_global_composite_op(_ctx(vg).c, int(op))


# ---------------------------------------------------------------------------
#  Scissor
# ---------------------------------------------------------------------------
def nvgScissor(vg, x, y, w, h):          _lib.nvgr_scissor(_ctx(vg).c, x, y, w, h)
def nvgIntersectScissor(vg, x, y, w, h): _lib.nvgr_intersect_scissor(_ctx(vg).c, x, y, w, h)
def nvgResetScissor(vg):                 _lib.nvgr_reset_scissor(_ctx(vg).c)


# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------
def nvgBeginPath(vg):                       _lib.nvgr_begin_path(_ctx(vg).c)
def nvgClosePath(vg):                       _lib.nvgr_close_path(_ctx(vg).c)
def nvgPathWinding(vg, dir):                _lib.nvgr_path_winding(_ctx(vg).c, int(dir))
def nvgMoveTo(vg, x, y):                    _lib.nvgr_move_to(_ctx(vg).c, x, y)
def nvgLineTo(vg, x, y):                    _lib.nvgr_line_to(_ctx(vg).c, x, y)
def nvgBezierTo(vg, c1x, c1y, c2x, c2y, x, y): _lib.nvgr_bezier_to(_ctx(vg).c, c1x,c1y,c2x,c2y,x,y)
def nvgQuadTo(vg, cx, cy, x, y):            _lib.nvgr_quad_to(_ctx(vg).c, cx,cy,x,y)
def nvgArcTo(vg, x1, y1, x2, y2, r):        _lib.nvgr_arc_to(_ctx(vg).c, x1,y1,x2,y2,r)
def nvgArc(vg, cx, cy, r, a0, a1, dir):     _lib.nvgr_arc(_ctx(vg).c, cx,cy,r,a0,a1,int(dir))
def nvgRect(vg, x, y, w, h):                _lib.nvgr_rect(_ctx(vg).c, x,y,w,h)
def nvgRoundedRect(vg, x, y, w, h, r):      _lib.nvgr_rounded_rect(_ctx(vg).c, x,y,w,h,r)
def nvgRoundedRectVarying(vg, x, y, w, h, rTL, rTR, rBR, rBL):
    _lib.nvgr_rounded_rect_varying(_ctx(vg).c, x,y,w,h,rTL,rTR,rBR,rBL)
def nvgEllipse(vg, cx, cy, rx, ry):         _lib.nvgr_ellipse(_ctx(vg).c, cx,cy,rx,ry)
def nvgCircle(vg, cx, cy, r):               _lib.nvgr_circle(_ctx(vg).c, cx,cy,r)


# ---------------------------------------------------------------------------
#  Fill / stroke
# ---------------------------------------------------------------------------
def nvgFillColor(vg, col):
    r,g,b,a = _col(col); _lib.nvgr_fill_color(_ctx(vg).c, r,g,b,a)
def nvgStrokeColor(vg, col):
    r,g,b,a = _col(col); _lib.nvgr_stroke_color(_ctx(vg).c, r,g,b,a)
def nvgStrokeWidth(vg, w):     _lib.nvgr_stroke_width(_ctx(vg).c, w)
def nvgMiterLimit(vg, l):      _lib.nvgr_miter_limit(_ctx(vg).c, l)
def nvgLineCap(vg, cap):       _lib.nvgr_line_cap(_ctx(vg).c, int(cap))
def nvgLineJoin(vg, j):        _lib.nvgr_line_join(_ctx(vg).c, int(j))
def nvgFill(vg):               _lib.nvgr_fill(_ctx(vg).c)
def nvgStroke(vg):             _lib.nvgr_stroke(_ctx(vg).c)


# ---------------------------------------------------------------------------
#  Paints
# ---------------------------------------------------------------------------
def nvgLinearGradient(vg, sx, sy, ex, ey, c1, c2):
    r1,g1,b1,a1 = _col(c1); r2,g2,b2,a2 = _col(c2)
    return _lib.nvgr_linear_gradient(_ctx(vg).c, sx,sy,ex,ey, r1,g1,b1,a1, r2,g2,b2,a2)

def nvgRadialGradient(vg, cx, cy, inr, outr, c1, c2):
    r1,g1,b1,a1 = _col(c1); r2,g2,b2,a2 = _col(c2)
    return _lib.nvgr_radial_gradient(_ctx(vg).c, cx,cy,inr,outr, r1,g1,b1,a1, r2,g2,b2,a2)

def nvgBoxGradient(vg, x, y, w, h, r, f, c1, c2):
    r1,g1,b1,a1 = _col(c1); r2,g2,b2,a2 = _col(c2)
    return _lib.nvgr_box_gradient(_ctx(vg).c, x,y,w,h,r,f, r1,g1,b1,a1, r2,g2,b2,a2)

def nvgImagePattern(vg, ox, oy, ew, eh, ang, image, alpha):
    return _lib.nvgr_image_pattern(_ctx(vg).c, ox,oy,ew,eh,ang, int(image), alpha)

def nvgFillPaint(vg, paint):   _lib.nvgr_fill_paint(_ctx(vg).c, int(paint))
def nvgStrokePaint(vg, paint): _lib.nvgr_stroke_paint(_ctx(vg).c, int(paint))


# ---------------------------------------------------------------------------
#  Fonts / text
# ---------------------------------------------------------------------------
def _resolve_path(asset_loader, path):
    """Mirror lua_preview's asset resolution: try cwd, then asset root."""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    # cwd is typically asset root (run.py chdir'd there)
    if os.path.exists(path):
        return os.path.abspath(path)
    if asset_loader is not None and getattr(asset_loader, "asset_root", None):
        cand = os.path.join(asset_loader.asset_root, path)
        if os.path.exists(cand):
            return cand
    return path  # last resort, let nanovg fail explicitly


def nvgCreateFont(vg, name, path):
    c = _ctx(vg)
    real = _resolve_path(c.asset_loader, str(path))
    fid = _lib.nvgr_create_font(c.c, str(name).encode("utf-8"), real.encode("utf-8"))
    if fid < 0 and c.font_loader is not None:
        # 字体文件找不到时，借用 pygame FontLoader 的降级路径（系统 CJK 字体）。
        try:
            c.font_loader.register(str(name), str(path))
            fb = c.font_loader._registered.get(str(name), "")
            if fb and os.path.exists(fb):
                fid = _lib.nvgr_create_font(c.c, str(name).encode("utf-8"), fb.encode("utf-8"))
                if fid >= 0:
                    print(f"[nvg-native] 字体 {name!r} 降级到 {fb}")
        except Exception:
            pass
    if fid >= 0:
        c._fonts[str(name)] = fid
    else:
        print(f"[nvg-native] nvgCreateFont({name!r}, {path!r}) failed")
    return fid

def nvgFindFont(vg, name):       return _lib.nvgr_find_font(_ctx(vg).c, str(name).encode("utf-8"))
def nvgAddFallbackFont(vg, base, fb):
    return _lib.nvgr_add_fallback_font(_ctx(vg).c, str(base).encode("utf-8"), str(fb).encode("utf-8"))
def nvgFontFace(vg, name):       _lib.nvgr_font_face(_ctx(vg).c, str(name).encode("utf-8"))
def nvgFontFaceId(vg, fid):      _lib.nvgr_font_face_id(_ctx(vg).c, int(fid))
def nvgFontSize(vg, size):       _lib.nvgr_font_size(_ctx(vg).c, size)
def nvgFontBlur(vg, b):          _lib.nvgr_font_blur(_ctx(vg).c, b)
def nvgTextAlign(vg, flags):     _lib.nvgr_text_align(_ctx(vg).c, int(flags))
def nvgTextLetterSpacing(vg, s): _lib.nvgr_text_letter_spacing(_ctx(vg).c, s)
def nvgTextLineHeight(vg, h):    _lib.nvgr_text_line_height(_ctx(vg).c, h)

def nvgText(vg, x, y, txt):
    s = str(txt).encode("utf-8")
    return _lib.nvgr_text(_ctx(vg).c, x, y, s, len(s))

def nvgTextBox(vg, x, y, breakw, txt):
    s = str(txt).encode("utf-8")
    _lib.nvgr_text_box(_ctx(vg).c, x, y, breakw, s, len(s))

def nvgTextBounds(vg, x, y, txt):
    s = str(txt).encode("utf-8")
    bounds = _ffi.new("float[4]")
    advance = _lib.nvgr_text_bounds(_ctx(vg).c, x, y, s, len(s), bounds)
    return advance, bounds[0], bounds[1], bounds[2], bounds[3]

def nvgTextBoxBounds(vg, x, y, breakw, txt):
    s = str(txt).encode("utf-8")
    bounds = _ffi.new("float[4]")
    _lib.nvgr_text_box_bounds(_ctx(vg).c, x, y, breakw, s, len(s), bounds)
    return bounds[0], bounds[1], bounds[2], bounds[3]

def nvgTextMetrics(vg):
    a = _ffi.new("float*"); d = _ffi.new("float*"); l = _ffi.new("float*")
    _lib.nvgr_text_metrics(_ctx(vg).c, a, d, l)
    return a[0], d[0], l[0]


# ---------------------------------------------------------------------------
#  Images
# ---------------------------------------------------------------------------
def nvgCreateImage(vg, path, flags):
    c = _ctx(vg)
    real = _resolve_path(c.asset_loader, str(path))
    h = _lib.nvgr_create_image(c.c, real.encode("utf-8"), int(flags) if flags else 0)
    if h <= 0:
        print(f"[nvg-native] nvgCreateImage({real!r}) failed")
    return h

def nvgImageSize(vg, h):
    w = _ffi.new("int*"); ht = _ffi.new("int*")
    _lib.nvgr_image_size(_ctx(vg).c, int(h), w, ht)
    return w[0], ht[0]

def nvgDeleteImage(vg, h): _lib.nvgr_delete_image(_ctx(vg).c, int(h))

def nvgUpdateImage(vg, h, data_bytes):
    buf = _ffi.from_buffer("uint8_t[]", data_bytes)
    _lib.nvgr_update_image(_ctx(vg).c, int(h), buf)


# ---------------------------------------------------------------------------
#  Compatibility no-ops (TapTap private extensions / context lifecycle)
# ---------------------------------------------------------------------------
# The game scripts may call these; in lua_preview they're inert because
# librender already owns the context and there's no Bloom/RT support.
def nvgCreate(*_a):                 return 1   # dummy non-nil handle
def nvgDelete(*_a):                 pass
def nvgSetBloomEnabled(*_a):        pass
def nvgSetColorSpace(*_a):          pass
def nvgSetRenderTarget(*_a):        pass
def nvgSetRenderOrder(*_a):         pass
def nvgImagePatternTinted(vg, ox, oy, ew, eh, ang, image, alpha, *_extra):
    return nvgImagePattern(vg, ox, oy, ew, eh, ang, image, alpha)
def nvgCreateVideo(*_a):            return -1
def nvgEllipseArc(vg, cx, cy, rx, ry, a0, a1, dir):
    # Approximate: draw a regular arc using mean radius. nanovg has no native ellipse arc.
    r = (float(rx) + float(ry)) * 0.5
    return nvgArc(vg, cx, cy, r, a0, a1, dir)
def nvgForceAutoHint(*_a):          pass
def nvgFontSizeMethod(*_a):         pass


# ---------------------------------------------------------------------------
#  Constants (matches NVG enum values used by game scripts)
# ---------------------------------------------------------------------------
NVG_CCW = 1
NVG_CW = 2
NVG_SOLID = 1
NVG_HOLE = 2
NVG_BUTT = 0
NVG_ROUND = 1
NVG_SQUARE = 2
NVG_BEVEL = 3
NVG_MITER = 4

NVG_ALIGN_LEFT     = 1 << 0
NVG_ALIGN_CENTER   = 1 << 1
NVG_ALIGN_RIGHT    = 1 << 2
NVG_ALIGN_TOP      = 1 << 3
NVG_ALIGN_MIDDLE   = 1 << 4
NVG_ALIGN_BOTTOM   = 1 << 5
NVG_ALIGN_BASELINE = 1 << 6
NVG_ALIGN_CENTER_VISUAL = 1 << 7

NVG_IMAGE_GENERATE_MIPMAPS = 1 << 0
NVG_IMAGE_REPEATX          = 1 << 1
NVG_IMAGE_REPEATY          = 1 << 2
NVG_IMAGE_FLIPY            = 1 << 3
NVG_IMAGE_PREMULTIPLIED    = 1 << 4
NVG_IMAGE_NEAREST          = 1 << 5

NVG_SOURCE_OVER = 0
NVG_SOURCE_IN = 1
NVG_SOURCE_OUT = 2
NVG_ATOP = 3
NVG_DESTINATION_OVER = 4
NVG_DESTINATION_IN = 5
NVG_DESTINATION_OUT = 6
NVG_DESTINATION_ATOP = 7
NVG_LIGHTER = 8
NVG_COPY = 9
NVG_XOR = 10

NVG_COLOR_GAMMA = 0
NVG_COLOR_LINEAR = 1


def install(lua):
    """Inject all nvg* functions and NVG_* constants into Lua globals."""
    g = lua.globals()
    for name, val in globals().items():
        if name.startswith("nvg") and callable(val):
            g[name] = val
        elif name.startswith("NVG_"):
            g[name] = val
