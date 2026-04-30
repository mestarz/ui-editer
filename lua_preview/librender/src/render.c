/*
 * librender for lua_preview
 * --------------------------
 * Headless OpenGL (OSMesa) + nanovg + nanovg_gl3.
 * Exposes a flat C ABI (one function per nanovg call, plus init/teardown
 * and a pixel-buffer accessor) that Python can drive via cffi.
 *
 * Design:
 *   - One process-wide OSMesa context + nanovg context.
 *   - Caller (Python) owns the framebuffer lifecycle through nvgr_resize.
 *   - Paints are owned by C; returned to caller as small integer handles
 *     valid only until the next nvgr_end_frame (cleared each frame).
 *   - All NVGcolor parameters are passed as 4 unsigned bytes (0..255)
 *     to keep the FFI surface trivial.
 *   - Strings are utf-8, null-terminated.
 *   - Coordinates and angles match nanovg (pixels, radians).
 */

/* OSMesa pulls in <GL/gl.h> before we get to set GL_GLEXT_PROTOTYPES.
 * Pre-declare it and pull glext so nanovg_gl can find the GL3 symbols. */
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <GL/glext.h>
#include <GL/osmesa.h>

#define NANOVG_GL3_IMPLEMENTATION
#include "nanovg.h"
#include "nanovg_gl.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define NVGR_API __attribute__((visibility("default")))

#define MAX_PAINTS 1024
struct ctx {
    OSMesaContext   osctx;
    NVGcontext     *vg;
    int             win_w, win_h;     /* logical px */
    float           dpr;
    int             fb_w, fb_h;       /* physical px = win * dpr */
    uint8_t        *fb;               /* RGBA, top-down, fb_w*fb_h*4 */
    NVGpaint        paints[MAX_PAINTS];
    int             paint_count;
};
typedef struct ctx ctx;

static NVGcolor col4u(uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
    NVGcolor c = {{{ r/255.f, g/255.f, b/255.f, a/255.f }}};
    return c;
}

static int alloc_fb(ctx *c) {
    free(c->fb);
    c->fb_w = (int)(c->win_w * c->dpr);
    c->fb_h = (int)(c->win_h * c->dpr);
    if (c->fb_w <= 0 || c->fb_h <= 0) return -1;
    c->fb = (uint8_t*)calloc((size_t)c->fb_w * c->fb_h * 4, 1);
    if (!c->fb) return -1;
    if (!OSMesaMakeCurrent(c->osctx, c->fb, GL_UNSIGNED_BYTE, c->fb_w, c->fb_h))
        return -1;
    /* Y_UP=0: framebuffer is top-down (matches pygame Surface). */
    OSMesaPixelStore(OSMESA_Y_UP, 0);
    glViewport(0, 0, c->fb_w, c->fb_h);
    return 0;
}

NVGR_API ctx *nvgr_init(int w, int h, float dpr) {
    ctx *c = (ctx*)calloc(1, sizeof(ctx));
    if (!c) return NULL;
    c->win_w = w; c->win_h = h; c->dpr = dpr > 0 ? dpr : 1.0f;
    c->osctx = OSMesaCreateContextExt(OSMESA_RGBA, 24, 8, 0, NULL);
    if (!c->osctx) { free(c); return NULL; }
    if (alloc_fb(c) != 0) { OSMesaDestroyContext(c->osctx); free(c); return NULL; }
    c->vg = nvgCreateGL3(NVG_ANTIALIAS | NVG_STENCIL_STROKES);
    if (!c->vg) { OSMesaDestroyContext(c->osctx); free(c->fb); free(c); return NULL; }
    return c;
}

NVGR_API int nvgr_resize(ctx *c, int w, int h, float dpr) {
    if (!c) return -1;
    c->win_w = w; c->win_h = h; c->dpr = dpr > 0 ? dpr : 1.0f;
    return alloc_fb(c);
}

NVGR_API void nvgr_destroy(ctx *c) {
    if (!c) return;
    if (c->vg) nvgDeleteGL3(c->vg);
    if (c->osctx) OSMesaDestroyContext(c->osctx);
    free(c->fb);
    free(c);
}

NVGR_API const uint8_t *nvgr_pixels(ctx *c) { return c ? c->fb : NULL; }
NVGR_API int nvgr_fb_width (ctx *c) { return c ? c->fb_w : 0; }
NVGR_API int nvgr_fb_height(ctx *c) { return c ? c->fb_h : 0; }

/* ---------- frame ---------- */
NVGR_API void nvgr_begin_frame(ctx *c) {
    if (!c) return;
    /* Bind framebuffer as current target each frame in case anything took it. */
    OSMesaMakeCurrent(c->osctx, c->fb, GL_UNSIGNED_BYTE, c->fb_w, c->fb_h);
    OSMesaPixelStore(OSMESA_Y_UP, 0);
    glViewport(0, 0, c->fb_w, c->fb_h);
    glClearColor(0, 0, 0, 0);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
    nvgBeginFrame(c->vg, (float)c->win_w, (float)c->win_h, c->dpr);
    c->paint_count = 0;
}
NVGR_API void nvgr_end_frame(ctx *c) {
    if (!c) return;
    nvgEndFrame(c->vg);
    glFinish();
    c->paint_count = 0;
}
NVGR_API void nvgr_cancel_frame(ctx *c) {
    if (!c) return;
    nvgCancelFrame(c->vg);
    c->paint_count = 0;
}

/* ---------- state stack / transforms ---------- */
NVGR_API void nvgr_save     (ctx *c) { nvgSave(c->vg); }
NVGR_API void nvgr_restore  (ctx *c) { nvgRestore(c->vg); }
NVGR_API void nvgr_reset    (ctx *c) { nvgReset(c->vg); }
NVGR_API void nvgr_translate(ctx *c, float x, float y) { nvgTranslate(c->vg, x, y); }
NVGR_API void nvgr_scale    (ctx *c, float sx, float sy){ nvgScale(c->vg, sx, sy); }
NVGR_API void nvgr_rotate   (ctx *c, float a)           { nvgRotate(c->vg, a); }
NVGR_API void nvgr_skew_x   (ctx *c, float a)           { nvgSkewX(c->vg, a); }
NVGR_API void nvgr_skew_y   (ctx *c, float a)           { nvgSkewY(c->vg, a); }
NVGR_API void nvgr_reset_transform(ctx *c)              { nvgResetTransform(c->vg); }
NVGR_API void nvgr_global_alpha(ctx *c, float a)        { nvgGlobalAlpha(c->vg, a); }
NVGR_API void nvgr_global_composite_op(ctx *c, int op)  { nvgGlobalCompositeOperation(c->vg, op); }

/* ---------- scissor ---------- */
NVGR_API void nvgr_scissor          (ctx *c, float x, float y, float w, float h) { nvgScissor(c->vg, x,y,w,h); }
NVGR_API void nvgr_intersect_scissor(ctx *c, float x, float y, float w, float h) { nvgIntersectScissor(c->vg, x,y,w,h); }
NVGR_API void nvgr_reset_scissor    (ctx *c) { nvgResetScissor(c->vg); }

/* ---------- paths ---------- */
NVGR_API void nvgr_begin_path  (ctx *c) { nvgBeginPath(c->vg); }
NVGR_API void nvgr_close_path  (ctx *c) { nvgClosePath(c->vg); }
NVGR_API void nvgr_path_winding(ctx *c, int dir) { nvgPathWinding(c->vg, dir); }

NVGR_API void nvgr_move_to    (ctx *c, float x, float y) { nvgMoveTo(c->vg, x, y); }
NVGR_API void nvgr_line_to    (ctx *c, float x, float y) { nvgLineTo(c->vg, x, y); }
NVGR_API void nvgr_bezier_to  (ctx *c, float c1x, float c1y, float c2x, float c2y, float x, float y) { nvgBezierTo(c->vg, c1x,c1y,c2x,c2y,x,y); }
NVGR_API void nvgr_quad_to    (ctx *c, float cx, float cy, float x, float y) { nvgQuadTo(c->vg, cx,cy,x,y); }
NVGR_API void nvgr_arc_to     (ctx *c, float x1, float y1, float x2, float y2, float radius) { nvgArcTo(c->vg, x1,y1,x2,y2,radius); }

NVGR_API void nvgr_arc        (ctx *c, float cx, float cy, float r, float a0, float a1, int dir) { nvgArc(c->vg, cx,cy,r,a0,a1,dir); }
NVGR_API void nvgr_rect       (ctx *c, float x, float y, float w, float h) { nvgRect(c->vg, x,y,w,h); }
NVGR_API void nvgr_rounded_rect(ctx *c, float x, float y, float w, float h, float r) { nvgRoundedRect(c->vg, x,y,w,h,r); }
NVGR_API void nvgr_rounded_rect_varying(ctx *c, float x, float y, float w, float h,
                                        float rTL, float rTR, float rBR, float rBL) {
    nvgRoundedRectVarying(c->vg, x,y,w,h,rTL,rTR,rBR,rBL);
}
NVGR_API void nvgr_ellipse    (ctx *c, float cx, float cy, float rx, float ry) { nvgEllipse(c->vg, cx,cy,rx,ry); }
NVGR_API void nvgr_circle     (ctx *c, float cx, float cy, float r) { nvgCircle(c->vg, cx,cy,r); }

/* ---------- fill / stroke ---------- */
NVGR_API void nvgr_fill_color  (ctx *c, uint8_t r, uint8_t g, uint8_t b, uint8_t a) { nvgFillColor(c->vg, col4u(r,g,b,a)); }
NVGR_API void nvgr_stroke_color(ctx *c, uint8_t r, uint8_t g, uint8_t b, uint8_t a) { nvgStrokeColor(c->vg, col4u(r,g,b,a)); }
NVGR_API void nvgr_stroke_width(ctx *c, float w) { nvgStrokeWidth(c->vg, w); }
NVGR_API void nvgr_miter_limit (ctx *c, float l) { nvgMiterLimit(c->vg, l); }
NVGR_API void nvgr_line_cap    (ctx *c, int cap) { nvgLineCap(c->vg, cap); }
NVGR_API void nvgr_line_join   (ctx *c, int j)   { nvgLineJoin(c->vg, j); }
NVGR_API void nvgr_fill        (ctx *c) { nvgFill(c->vg); }
NVGR_API void nvgr_stroke      (ctx *c) { nvgStroke(c->vg); }

/* ---------- paints (returned as small integer handles, valid until end_frame) ---------- */
static int push_paint(ctx *c, NVGpaint p) {
    if (c->paint_count >= MAX_PAINTS) return -1;
    int id = c->paint_count++;
    c->paints[id] = p;
    return id;
}
NVGR_API int nvgr_linear_gradient(ctx *c, float sx, float sy, float ex, float ey,
                                  uint8_t r1, uint8_t g1, uint8_t b1, uint8_t a1,
                                  uint8_t r2, uint8_t g2, uint8_t b2, uint8_t a2) {
    return push_paint(c, nvgLinearGradient(c->vg, sx,sy,ex,ey, col4u(r1,g1,b1,a1), col4u(r2,g2,b2,a2)));
}
NVGR_API int nvgr_radial_gradient(ctx *c, float cx, float cy, float inr, float outr,
                                  uint8_t r1, uint8_t g1, uint8_t b1, uint8_t a1,
                                  uint8_t r2, uint8_t g2, uint8_t b2, uint8_t a2) {
    return push_paint(c, nvgRadialGradient(c->vg, cx,cy,inr,outr, col4u(r1,g1,b1,a1), col4u(r2,g2,b2,a2)));
}
NVGR_API int nvgr_box_gradient(ctx *c, float x, float y, float w, float h, float r, float f,
                               uint8_t r1, uint8_t g1, uint8_t b1, uint8_t a1,
                               uint8_t r2, uint8_t g2, uint8_t b2, uint8_t a2) {
    return push_paint(c, nvgBoxGradient(c->vg, x,y,w,h,r,f, col4u(r1,g1,b1,a1), col4u(r2,g2,b2,a2)));
}
NVGR_API int nvgr_image_pattern(ctx *c, float ox, float oy, float ew, float eh, float angle,
                                int image, float alpha) {
    return push_paint(c, nvgImagePattern(c->vg, ox,oy,ew,eh,angle,image,alpha));
}
NVGR_API void nvgr_fill_paint  (ctx *c, int paint_id) {
    if (paint_id < 0 || paint_id >= c->paint_count) return;
    nvgFillPaint(c->vg, c->paints[paint_id]);
}
NVGR_API void nvgr_stroke_paint(ctx *c, int paint_id) {
    if (paint_id < 0 || paint_id >= c->paint_count) return;
    nvgStrokePaint(c->vg, c->paints[paint_id]);
}

/* ---------- fonts / text ---------- */
NVGR_API int  nvgr_create_font     (ctx *c, const char *name, const char *path) { return nvgCreateFont(c->vg, name, path); }
NVGR_API int  nvgr_find_font       (ctx *c, const char *name) { return nvgFindFont(c->vg, name); }
NVGR_API int  nvgr_add_fallback_font(ctx *c, const char *base_name, const char *fallback_name) {
    return nvgAddFallbackFont(c->vg, base_name, fallback_name);
}
NVGR_API void nvgr_font_face   (ctx *c, const char *name) { nvgFontFace(c->vg, name); }
NVGR_API void nvgr_font_face_id(ctx *c, int font_id) { nvgFontFaceId(c->vg, font_id); }
NVGR_API void nvgr_font_size   (ctx *c, float size) { nvgFontSize(c->vg, size); }
NVGR_API void nvgr_font_blur   (ctx *c, float b) { nvgFontBlur(c->vg, b); }
NVGR_API void nvgr_text_align  (ctx *c, int align) { nvgTextAlign(c->vg, align); }
NVGR_API void nvgr_text_letter_spacing(ctx *c, float s) { nvgTextLetterSpacing(c->vg, s); }
NVGR_API void nvgr_text_line_height   (ctx *c, float h) { nvgTextLineHeight(c->vg, h); }
NVGR_API float nvgr_text(ctx *c, float x, float y, const char *s, int len) {
    const char *end = (len < 0) ? NULL : s + len;
    return nvgText(c->vg, x, y, s, end);
}
NVGR_API void nvgr_text_box(ctx *c, float x, float y, float break_w, const char *s, int len) {
    const char *end = (len < 0) ? NULL : s + len;
    nvgTextBox(c->vg, x, y, break_w, s, end);
}
NVGR_API float nvgr_text_bounds(ctx *c, float x, float y, const char *s, int len, float bounds_out[4]) {
    const char *end = (len < 0) ? NULL : s + len;
    return nvgTextBounds(c->vg, x, y, s, end, bounds_out);
}
NVGR_API void nvgr_text_box_bounds(ctx *c, float x, float y, float break_w, const char *s, int len, float bounds_out[4]) {
    const char *end = (len < 0) ? NULL : s + len;
    nvgTextBoxBounds(c->vg, x, y, break_w, s, end, bounds_out);
}
NVGR_API void nvgr_text_metrics(ctx *c, float *ascender, float *descender, float *lineh) {
    nvgTextMetrics(c->vg, ascender, descender, lineh);
}

/* ---------- images ---------- */
NVGR_API int  nvgr_create_image     (ctx *c, const char *path, int flags)   { return nvgCreateImage(c->vg, path, flags); }
NVGR_API int  nvgr_create_image_mem (ctx *c, int flags, const uint8_t *data, int n) { return nvgCreateImageMem(c->vg, flags, (unsigned char*)data, n); }
NVGR_API int  nvgr_create_image_rgba(ctx *c, int w, int h, int flags, const uint8_t *data) { return nvgCreateImageRGBA(c->vg, w, h, flags, data); }
NVGR_API void nvgr_update_image     (ctx *c, int image, const uint8_t *data) { nvgUpdateImage(c->vg, image, data); }
NVGR_API void nvgr_image_size       (ctx *c, int image, int *w, int *h) { nvgImageSize(c->vg, image, w, h); }
NVGR_API void nvgr_delete_image     (ctx *c, int image) { nvgDeleteImage(c->vg, image); }

/* ---------- transforms (introspection) ---------- */
NVGR_API void nvgr_current_transform(ctx *c, float xform[6]) { nvgCurrentTransform(c->vg, xform); }

/* ---------- utils ---------- */
NVGR_API float nvgr_deg_to_rad(float deg) { return nvgDegToRad(deg); }
NVGR_API float nvgr_rad_to_deg(float rad) { return nvgRadToDeg(rad); }
