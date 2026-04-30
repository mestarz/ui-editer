/* nvg_renderer — headless NanoVG renderer driven by user Lua code.
 *
 * Usage:
 *   echo 'nvgBeginPath(vg) nvgRect(vg,10,10,100,100) nvgFillColor(vg,nvgRGB(255,0,0)) nvgFill(vg)' \
 *     | nvg_renderer --width 256 --height 256 --dpr 1 --assets ./assets
 *
 * Lua execution model: BeginFrame/EndFrame are issued by the host. The user
 * script is wrapped so that its top-level code runs between them. If the user
 * defines `function draw(vg, w, h)` it is invoked with those args.
 *
 * Output: PNG bytes on stdout. Errors and logs on stderr. Exit codes:
 *   0 success
 *   1 init error (OSMesa / GL / nanovg)
 *   2 lua error
 *   3 io error
 */

#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <getopt.h>

#define GL_GLEXT_PROTOTYPES 1
#include <GL/gl.h>
#include <GL/glext.h>
#include <GL/osmesa.h>

#define NANOVG_GL3_IMPLEMENTATION
#include "nanovg.h"
#include "nanovg_gl.h"

#include "lua.h"
#include "lualib.h"
#include "lauxlib.h"

#include "lua_nvg.h"
#include "png_writer.h"

static void die(int code, const char *msg) {
    fprintf(stderr, "nvg_renderer: %s\n", msg);
    exit(code);
}

static char *read_all_stdin(size_t *out_len) {
    size_t cap = 4096, len = 0;
    char *buf = (char *)malloc(cap);
    if (!buf) die(3, "oom");
    for (;;) {
        if (len + 4096 > cap) { cap *= 2; buf = (char *)realloc(buf, cap); if (!buf) die(3,"oom"); }
        ssize_t n = read(0, buf + len, cap - len);
        if (n < 0) die(3, "stdin read failed");
        if (n == 0) break;
        len += (size_t)n;
    }
    buf[len] = 0;
    *out_len = len;
    return buf;
}

/* Vertically flip rows of an RGBA8 image in place. nanovg's GL output and
 * OSMesa's framebuffer both have origin at lower-left; PNG wants top-left. */
static void flip_y_rgba(unsigned char *p, int w, int h) {
    int stride = w * 4;
    unsigned char *row = (unsigned char *)malloc(stride);
    for (int y = 0; y < h / 2; y++) {
        unsigned char *a = p + y * stride;
        unsigned char *b = p + (h - 1 - y) * stride;
        memcpy(row, a, stride);
        memcpy(a, b, stride);
        memcpy(b, row, stride);
    }
    free(row);
}

int main(int argc, char **argv) {
    int width = 512, height = 512;
    float dpr = 1.0f;
    const char *assets_dir = ".";
    const char *default_font = NULL;
    const char *script_path = NULL;
    double time_sec = 0.0;

    static struct option opts[] = {
        {"width",  required_argument, 0, 'w'},
        {"height", required_argument, 0, 'h'},
        {"dpr",    required_argument, 0, 'd'},
        {"assets", required_argument, 0, 'a'},
        {"font",   required_argument, 0, 'f'},
        {"script", required_argument, 0, 's'},
        {"time",   required_argument, 0, 't'},
        {0,0,0,0}
    };
    int c, idx;
    while ((c = getopt_long(argc, argv, "w:h:d:a:f:s:t:", opts, &idx)) != -1) {
        switch (c) {
            case 'w': width  = atoi(optarg); break;
            case 'h': height = atoi(optarg); break;
            case 'd': dpr    = (float)atof(optarg); break;
            case 'a': assets_dir = optarg; break;
            case 'f': default_font = optarg; break;
            case 's': script_path = optarg; break;
            case 't': time_sec = atof(optarg); break;
            default: die(1, "bad args");
        }
    }
    if (width  <= 0 || width  > 8192) die(1, "width out of range");
    if (height <= 0 || height > 8192) die(1, "height out of range");

    /* OSMesa context (32-bit RGBA, 24-bit depth, 8-bit stencil). */
    OSMesaContext osctx = OSMesaCreateContextExt(OSMESA_RGBA, 24, 8, 0, NULL);
    if (!osctx) die(1, "OSMesaCreateContextExt failed");

    int fb_w = (int)(width  * dpr);
    int fb_h = (int)(height * dpr);
    unsigned char *fb = (unsigned char *)calloc((size_t)fb_w * fb_h * 4, 1);
    if (!fb) die(1, "framebuffer alloc failed");

    if (!OSMesaMakeCurrent(osctx, fb, GL_UNSIGNED_BYTE, fb_w, fb_h)) {
        die(1, "OSMesaMakeCurrent failed");
    }
    /* OSMesa default origin is lower-left; that's what nanovg_gl expects. */
    OSMesaPixelStore(OSMESA_Y_UP, 1);

    NVGcontext *vg = nvgCreateGL3(NVG_ANTIALIAS | NVG_STENCIL_STROKES);
    if (!vg) die(1, "nvgCreateGL3 failed");

    glViewport(0, 0, fb_w, fb_h);
    glClearColor(0, 0, 0, 0);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);

    /* Lua state */
    lua_State *L = luaL_newstate();
    if (!L) die(1, "luaL_newstate failed");
    luaL_openlibs(L);
    lua_nvg_open(L, vg);

    /* Make assets dir available to user scripts */
    lua_pushstring(L, assets_dir);
    lua_setglobal(L, "ASSETS_DIR");
    lua_pushinteger(L, width);  lua_setglobal(L, "WIDTH");
    lua_pushinteger(L, height); lua_setglobal(L, "HEIGHT");
    lua_pushnumber(L,  dpr);    lua_setglobal(L, "DPR");
    lua_pushnumber(L,  time_sec); lua_setglobal(L, "T");

    /* Pre-load default font as "default" */
    if (default_font && *default_font) {
        if (nvgCreateFont(vg, "default", default_font) < 0) {
            fprintf(stderr, "warn: failed to load default font: %s\n", default_font);
        }
    }

    /* Read user script */
    char *script = NULL; size_t script_len = 0;
    if (script_path) {
        FILE *f = fopen(script_path, "rb");
        if (!f) die(3, "cannot open script");
        fseek(f, 0, SEEK_END); script_len = ftell(f); fseek(f, 0, SEEK_SET);
        script = (char *)malloc(script_len + 1);
        if (fread(script, 1, script_len, f) != script_len) die(3, "script read failed");
        script[script_len] = 0;
        fclose(f);
    } else {
        script = read_all_stdin(&script_len);
    }

    /* Begin frame, run script, end frame */
    nvgBeginFrame(vg, (float)width, (float)height, dpr);

    if (luaL_loadbuffer(L, script, script_len, "user") != LUA_OK) {
        fprintf(stderr, "lua load: %s\n", lua_tostring(L, -1));
        nvgCancelFrame(vg);
        return 2;
    }
    if (lua_pcall(L, 0, 0, 0) != LUA_OK) {
        fprintf(stderr, "lua run: %s\n", lua_tostring(L, -1));
        nvgCancelFrame(vg);
        return 2;
    }
    /* Optional draw(vg, w, h) */
    lua_getglobal(L, "draw");
    if (lua_isfunction(L, -1)) {
        lua_pushlightuserdata(L, vg);
        lua_pushinteger(L, width);
        lua_pushinteger(L, height);
        lua_pushnumber(L, time_sec);
        if (lua_pcall(L, 4, 0, 0) != LUA_OK) {
            fprintf(stderr, "lua draw(): %s\n", lua_tostring(L, -1));
            nvgCancelFrame(vg);
            return 2;
        }
    } else {
        lua_pop(L, 1);
    }

    nvgEndFrame(vg);
    glFinish();

    /* PNG */
    flip_y_rgba(fb, fb_w, fb_h);
    unsigned char *png = NULL; size_t png_len = 0;
    if (png_encode_rgba(fb, fb_w, fb_h, fb_w * 4, &png, &png_len) != 0) {
        die(3, "png encode failed");
    }
    if (fwrite(png, 1, png_len, stdout) != png_len) die(3, "stdout write failed");
    fflush(stdout);

    free(png);
    free(fb);
    free(script);
    lua_close(L);
    nvgDeleteGL3(vg);
    OSMesaDestroyContext(osctx);
    return 0;
}
