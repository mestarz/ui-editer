/*
 * librender_egl for lua_preview
 * -----------------------------
 * Headless OpenGL via EGL device platform (EGL_EXT_platform_device).
 * Same flat C ABI as the OSMesa-based ../librender, so engine_shim/nvg.py
 * can load either one.
 *
 * Why a separate sibling project (instead of #ifdef inside librender)?
 *   - Mesa 26+ no longer ships OSMesa; the OSMesa build path is dead on
 *     fresh Arch / Fedora installs. WSL/Debian still ship libosmesa6-dev,
 *     so ../librender stays useful there.
 *   - Keeping the two backends in physically separate trees avoids any
 *     risk of toolchain mix-ups (one build only ever touches one GL stack).
 *
 * Isolation strategy:
 *   - We open a *device* EGLDisplay (eglGetPlatformDisplayEXT with
 *     EGL_PLATFORM_DEVICE_EXT). It is independent from any wayland/x11
 *     EGLDisplay the host app (e.g. SDL2) might be using, so our context
 *     never invalidates the host's "current" context.
 *   - Render target is an FBO (RGBA8 + depth24_stencil8). After each frame
 *     we glReadPixels into the caller-owned framebuffer (top-down).
 *   - eglMakeCurrent(NO_*) is called on every public boundary so any
 *     stray EGL state we touched is released back to the driver.
 */

#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <GL/glext.h>

#include <EGL/egl.h>
#include <EGL/eglext.h>

#define NANOVG_GL3_IMPLEMENTATION
#include "nanovg.h"
#include "nanovg_gl.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define NVGR_API __attribute__((visibility("default")))

#define MAX_PAINTS 1024

/* The host process (SDL2 wayland driver) may itself be using EGL for its
 * window surface. eglMakeCurrent is per-thread state, so any change we make
 * also affects the host. We snapshot the host's "current" tuple on entry
 * and restore it on exit, so SDL's own EGL operations remain valid.        */
struct egl_save { EGLDisplay dpy; EGLContext ctx; EGLSurface draw, read; };

struct ctx {
    /* EGL */
    EGLDisplay      dpy;
    EGLContext      egl_ctx;
    EGLConfig       egl_cfg;
    EGLSurface      egl_surf;       /* EGL_NO_SURFACE if surfaceless */
    int             surfaceless;

    /* GL render target */
    GLuint          fbo;
    GLuint          color_rb;
    GLuint          depth_rb;

    /* nanovg */
    NVGcontext     *vg;

    /* Geometry & framebuffer mirror exposed to Python. */
    int             win_w, win_h;     /* logical px */
    float           dpr;
    int             fb_w, fb_h;       /* physical px = win * dpr */
    uint8_t        *fb;               /* RGBA, top-down, fb_w*fb_h*4 */
    uint8_t        *scratch;          /* same size; bottom-up read target */

    NVGpaint        paints[MAX_PAINTS];
    int             paint_count;

    /* Host EGL state captured at begin_frame, restored at end/cancel_frame. */
    struct egl_save frame_save;
};
typedef struct ctx ctx;

static NVGcolor col4u(uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
    NVGcolor c = {{{ r/255.f, g/255.f, b/255.f, a/255.f }}};
    return c;
}

/* ------------------------------------------------------------------ */
/*  EGL helpers                                                        */
/* ------------------------------------------------------------------ */

static int has_ext(const char *exts, const char *name) {
    if (!exts || !name) return 0;
    size_t n = strlen(name);
    const char *p = exts;
    while ((p = strstr(p, name)) != NULL) {
        char before = (p == exts) ? ' ' : *(p - 1);
        char after  = p[n];
        if ((before == ' ' || before == '\0') && (after == ' ' || after == '\0'))
            return 1;
        p += n;
    }
    return 0;
}

/* Open an EGL display that does not collide with whatever the host process
 * (SDL/pygame/etc.) might have. We try, in order:
 *   1) eglGetPlatformDisplayEXT(EGL_PLATFORM_DEVICE_EXT, dev_i)        -- per device
 *   2) eglGetPlatformDisplayEXT(EGL_PLATFORM_SURFACELESS_MESA, NULL)   -- Mesa swrast
 *   3) eglGetDisplay(EGL_DEFAULT_DISPLAY)                              -- last resort
 * Each candidate is only accepted after eglInitialize succeeds, because on
 * Mesa+NVIDIA the device path may produce a display that fails to init.
 */
#ifndef EGL_PLATFORM_SURFACELESS_MESA
#define EGL_PLATFORM_SURFACELESS_MESA 0x31DD
#endif

static EGLDisplay try_init(EGLDisplay d, EGLint *out_maj, EGLint *out_min) {
    if (d == EGL_NO_DISPLAY) return EGL_NO_DISPLAY;
    if (eglInitialize(d, out_maj, out_min)) return d;
    return EGL_NO_DISPLAY;
}

static EGLDisplay open_device_display(EGLint *out_maj, EGLint *out_min) {
    const char *client_exts = eglQueryString(EGL_NO_DISPLAY, EGL_EXTENSIONS);
    int have_dev_query  = client_exts && has_ext(client_exts, "EGL_EXT_device_query");
    int have_dev_base   = client_exts && has_ext(client_exts, "EGL_EXT_device_base");
    int have_platform   = client_exts &&
        (has_ext(client_exts, "EGL_EXT_platform_device") ||
         has_ext(client_exts, "EGL_KHR_platform_device") ||
         has_ext(client_exts, "EGL_EXT_platform_base"));
    int have_surfaceless_mesa = client_exts &&
        has_ext(client_exts, "EGL_MESA_platform_surfaceless");

    PFNEGLQUERYDEVICESEXTPROC pQueryDevices =
        (PFNEGLQUERYDEVICESEXTPROC)eglGetProcAddress("eglQueryDevicesEXT");
    PFNEGLGETPLATFORMDISPLAYEXTPROC pGetPlatformDisplay =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");

    /* (1) Per-device displays: walk all advertised devices, pick the first
     * one that successfully initializes. On hybrid NVIDIA+Mesa systems the
     * NVIDIA device often fails ("driver (null)") and llvmpipe is later in
     * the list. */
    if ((have_dev_query || have_dev_base) && have_platform &&
        pQueryDevices && pGetPlatformDisplay) {
        EGLDeviceEXT devs[16];
        EGLint ndev = 0;
        if (pQueryDevices(16, devs, &ndev) && ndev > 0) {
            for (EGLint i = 0; i < ndev; i++) {
                EGLDisplay d = pGetPlatformDisplay(EGL_PLATFORM_DEVICE_EXT,
                                                   devs[i], NULL);
                EGLDisplay ok = try_init(d, out_maj, out_min);
                if (ok != EGL_NO_DISPLAY) return ok;
            }
        }
    }

    /* (2) Mesa surfaceless platform -- pure llvmpipe, no GPU needed.
     * Available on all modern Mesa builds. */
    if (have_surfaceless_mesa && pGetPlatformDisplay) {
        EGLDisplay d = pGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA,
                                           EGL_DEFAULT_DISPLAY, NULL);
        EGLDisplay ok = try_init(d, out_maj, out_min);
        if (ok != EGL_NO_DISPLAY) return ok;
    }

    /* (3) Plain default display. May share with host EGL apps; we still try
     * hard to release current state on every public boundary below. */
    EGLDisplay d = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    return try_init(d, out_maj, out_min);
}

/* ------------------------------------------------------------------ */
/*  GL render target                                                   */
/* ------------------------------------------------------------------ */

/* The host process (SDL2 wayland driver) may itself be using EGL for its
 * window surface. eglMakeCurrent is per-thread state, so any change we make
 * also affects the host. We snapshot the host's "current" tuple on entry
 * and restore it on exit, so SDL's own EGL operations remain valid.        */
static void save_current(struct egl_save *s) {
    s->dpy  = eglGetCurrentDisplay();
    s->ctx  = eglGetCurrentContext();
    s->draw = eglGetCurrentSurface(EGL_DRAW);
    s->read = eglGetCurrentSurface(EGL_READ);
}

static void restore_current(const struct egl_save *s) {
    if (s->dpy != EGL_NO_DISPLAY && s->ctx != EGL_NO_CONTEXT) {
        eglMakeCurrent(s->dpy, s->draw, s->read, s->ctx);
    } else {
        /* Host had nothing current -- leave nothing current.  We must use
         * *some* display for eglMakeCurrent(NO/NO/NO); pick our own. */
        EGLDisplay any = (s->dpy != EGL_NO_DISPLAY) ? s->dpy : EGL_NO_DISPLAY;
        if (any != EGL_NO_DISPLAY)
            eglMakeCurrent(any, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    }
}

static int make_current(ctx *c) {
    EGLBoolean ok;
    if (c->surfaceless)
        ok = eglMakeCurrent(c->dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, c->egl_ctx);
    else
        ok = eglMakeCurrent(c->dpy, c->egl_surf, c->egl_surf, c->egl_ctx);
    return ok ? 0 : -1;
}

static void release_current(ctx *c) {
    if (c && c->dpy != EGL_NO_DISPLAY)
        eglMakeCurrent(c->dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
}

static void destroy_target(ctx *c) {
    if (c->fbo)      { glDeleteFramebuffers(1, &c->fbo);   c->fbo = 0; }
    if (c->color_rb) { glDeleteRenderbuffers(1, &c->color_rb); c->color_rb = 0; }
    if (c->depth_rb) { glDeleteRenderbuffers(1, &c->depth_rb); c->depth_rb = 0; }
}

static int alloc_target(ctx *c) {
    destroy_target(c);

    glGenFramebuffers(1, &c->fbo);
    glGenRenderbuffers(1, &c->color_rb);
    glGenRenderbuffers(1, &c->depth_rb);

    glBindRenderbuffer(GL_RENDERBUFFER, c->color_rb);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA8, c->fb_w, c->fb_h);

    glBindRenderbuffer(GL_RENDERBUFFER, c->depth_rb);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, c->fb_w, c->fb_h);

    glBindFramebuffer(GL_FRAMEBUFFER, c->fbo);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                              GL_RENDERBUFFER, c->color_rb);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT,
                              GL_RENDERBUFFER, c->depth_rb);

    GLenum st = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    if (st != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(stderr, "[librender_egl] FBO incomplete: 0x%x\n", st);
        return -1;
    }
    glViewport(0, 0, c->fb_w, c->fb_h);
    return 0;
}

static int alloc_fb(ctx *c) {
    free(c->fb);     c->fb = NULL;
    free(c->scratch); c->scratch = NULL;
    c->fb_w = (int)(c->win_w * c->dpr);
    c->fb_h = (int)(c->win_h * c->dpr);
    if (c->fb_w <= 0 || c->fb_h <= 0) return -1;
    size_t sz = (size_t)c->fb_w * c->fb_h * 4;
    c->fb      = (uint8_t*)calloc(sz, 1);
    c->scratch = (uint8_t*)malloc(sz);
    if (!c->fb || !c->scratch) return -1;

    if (make_current(c) != 0) return -1;
    if (alloc_target(c) != 0) return -1;
    return 0;
}

/* ------------------------------------------------------------------ */
/*  Lifecycle                                                          */
/* ------------------------------------------------------------------ */

NVGR_API ctx *nvgr_init(int w, int h, float dpr) {
    ctx *c = (ctx*)calloc(1, sizeof(ctx));
    if (!c) return NULL;
    c->win_w = w; c->win_h = h; c->dpr = dpr > 0 ? dpr : 1.0f;
    c->dpy = EGL_NO_DISPLAY;
    c->egl_ctx = EGL_NO_CONTEXT;
    c->egl_surf = EGL_NO_SURFACE;
    EGLint maj = 0, min = 0;

    /* Save host's EGL current state, since eglInitialize/eglMakeCurrent
     * below will mutate per-thread EGL state. */
    struct egl_save host;
    save_current(&host);

    c->dpy = open_device_display(&maj, &min);
    if (c->dpy == EGL_NO_DISPLAY) {
        fprintf(stderr, "[librender_egl] could not initialize any EGL display\n");
        free(c); return NULL;
    }

    if (!eglBindAPI(EGL_OPENGL_API)) {
        fprintf(stderr, "[librender_egl] eglBindAPI(OPENGL) failed: 0x%x\n", eglGetError());
        eglTerminate(c->dpy); free(c); return NULL;
    }

    EGLint cfg_attr[] = {
        EGL_SURFACE_TYPE,    EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_DEPTH_SIZE, 24, EGL_STENCIL_SIZE, 8,
        EGL_NONE
    };
    EGLint ncfg = 0;
    if (!eglChooseConfig(c->dpy, cfg_attr, &c->egl_cfg, 1, &ncfg) || ncfg < 1) {
        fprintf(stderr, "[librender_egl] eglChooseConfig failed: 0x%x\n", eglGetError());
        eglTerminate(c->dpy); free(c); return NULL;
    }

    EGLint ctx_attr[] = {
        EGL_CONTEXT_MAJOR_VERSION, 3,
        EGL_CONTEXT_MINOR_VERSION, 3,
        EGL_CONTEXT_OPENGL_PROFILE_MASK,
            EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT,
        EGL_NONE
    };
    c->egl_ctx = eglCreateContext(c->dpy, c->egl_cfg, EGL_NO_CONTEXT, ctx_attr);
    if (c->egl_ctx == EGL_NO_CONTEXT) {
        /* Driver doesn't like core-profile request -- retry with no profile. */
        EGLint fallback_attr[] = { EGL_NONE };
        c->egl_ctx = eglCreateContext(c->dpy, c->egl_cfg, EGL_NO_CONTEXT, fallback_attr);
    }
    if (c->egl_ctx == EGL_NO_CONTEXT) {
        fprintf(stderr, "[librender_egl] eglCreateContext failed: 0x%x\n", eglGetError());
        eglTerminate(c->dpy); free(c); return NULL;
    }

    const char *dpy_exts = eglQueryString(c->dpy, EGL_EXTENSIONS);
    c->surfaceless = dpy_exts && has_ext(dpy_exts, "EGL_KHR_surfaceless_context");
    if (!c->surfaceless) {
        EGLint pb_attr[] = { EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE };
        c->egl_surf = eglCreatePbufferSurface(c->dpy, c->egl_cfg, pb_attr);
        if (c->egl_surf == EGL_NO_SURFACE) {
            fprintf(stderr, "[librender_egl] eglCreatePbufferSurface failed: 0x%x\n",
                    eglGetError());
            eglDestroyContext(c->dpy, c->egl_ctx); eglTerminate(c->dpy);
            free(c); return NULL;
        }
    }

    if (alloc_fb(c) != 0) {
        if (c->egl_surf != EGL_NO_SURFACE) eglDestroySurface(c->dpy, c->egl_surf);
        eglDestroyContext(c->dpy, c->egl_ctx);
        eglTerminate(c->dpy);
        free(c->fb); free(c->scratch); free(c);
        return NULL;
    }

    c->vg = nvgCreateGL3(NVG_ANTIALIAS | NVG_STENCIL_STROKES);
    if (!c->vg) {
        destroy_target(c);
        if (c->egl_surf != EGL_NO_SURFACE) eglDestroySurface(c->dpy, c->egl_surf);
        eglDestroyContext(c->dpy, c->egl_ctx);
        eglTerminate(c->dpy);
        free(c->fb); free(c->scratch); free(c);
        return NULL;
    }

    release_current(c);
    restore_current(&host);
    return c;
}

NVGR_API int nvgr_resize(ctx *c, int w, int h, float dpr) {
    if (!c) return -1;
    struct egl_save s; save_current(&s);
    c->win_w = w; c->win_h = h; c->dpr = dpr > 0 ? dpr : 1.0f;
    int rc = alloc_fb(c);
    restore_current(&s);
    return rc;
}

NVGR_API void nvgr_destroy(ctx *c) {
    if (!c) return;
    if (c->dpy != EGL_NO_DISPLAY) {
        struct egl_save s; save_current(&s);
        make_current(c);
        if (c->vg) nvgDeleteGL3(c->vg);
        destroy_target(c);
        restore_current(&s);
        if (c->egl_surf != EGL_NO_SURFACE) eglDestroySurface(c->dpy, c->egl_surf);
        if (c->egl_ctx  != EGL_NO_CONTEXT) eglDestroyContext(c->dpy, c->egl_ctx);
        eglTerminate(c->dpy);
    }
    free(c->fb);
    free(c->scratch);
    free(c);
}

NVGR_API const uint8_t *nvgr_pixels(ctx *c) { return c ? c->fb : NULL; }
NVGR_API int nvgr_fb_width (ctx *c) { return c ? c->fb_w : 0; }
NVGR_API int nvgr_fb_height(ctx *c) { return c ? c->fb_h : 0; }

/* ---------- frame ---------- */
NVGR_API void nvgr_begin_frame(ctx *c) {
    if (!c) return;
    save_current(&c->frame_save);
    make_current(c);
    glBindFramebuffer(GL_FRAMEBUFFER, c->fbo);
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
    /* Read back into scratch (bottom-up), then row-flip into c->fb (top-down,
     * matching pygame Surface and the OSMesa Y_UP=0 layout). */
    glBindFramebuffer(GL_READ_FRAMEBUFFER, c->fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, c->fb_w, c->fb_h, GL_RGBA, GL_UNSIGNED_BYTE, c->scratch);
    const int row = c->fb_w * 4;
    for (int y = 0; y < c->fb_h; y++) {
        memcpy(c->fb + y * row, c->scratch + (c->fb_h - 1 - y) * row, (size_t)row);
    }
    c->paint_count = 0;
    restore_current(&c->frame_save);
}

NVGR_API void nvgr_cancel_frame(ctx *c) {
    if (!c) return;
    nvgCancelFrame(c->vg);
    c->paint_count = 0;
    restore_current(&c->frame_save);
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

/* ---------- images ----------
 * These touch GL (glTexImage2D / glDeleteTextures) and may be invoked
 * outside of begin/end_frame (e.g. during asset preloading). Wrap each
 * call so our EGL context is current for the duration. */
#define WITH_GL(c, expr) do { \
    struct egl_save _s; save_current(&_s); \
    make_current(c); \
    expr; \
    restore_current(&_s); \
} while (0)

NVGR_API int  nvgr_create_image     (ctx *c, const char *path, int flags) {
    int r; WITH_GL(c, r = nvgCreateImage(c->vg, path, flags)); return r;
}
NVGR_API int  nvgr_create_image_mem (ctx *c, int flags, const uint8_t *data, int n) {
    int r; WITH_GL(c, r = nvgCreateImageMem(c->vg, flags, (unsigned char*)data, n)); return r;
}
NVGR_API int  nvgr_create_image_rgba(ctx *c, int w, int h, int flags, const uint8_t *data) {
    int r; WITH_GL(c, r = nvgCreateImageRGBA(c->vg, w, h, flags, data)); return r;
}
NVGR_API void nvgr_update_image     (ctx *c, int image, const uint8_t *data) {
    WITH_GL(c, nvgUpdateImage(c->vg, image, data));
}
NVGR_API void nvgr_image_size       (ctx *c, int image, int *w, int *h) { nvgImageSize(c->vg, image, w, h); }
NVGR_API void nvgr_delete_image     (ctx *c, int image) {
    WITH_GL(c, nvgDeleteImage(c->vg, image));
}

/* ---------- transforms (introspection) ---------- */
NVGR_API void nvgr_current_transform(ctx *c, float xform[6]) { nvgCurrentTransform(c->vg, xform); }

/* ---------- utils ---------- */
NVGR_API float nvgr_deg_to_rad(float deg) { return nvgDegToRad(deg); }
NVGR_API float nvgr_rad_to_deg(float rad) { return nvgRadToDeg(rad); }
