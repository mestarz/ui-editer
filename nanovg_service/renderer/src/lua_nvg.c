/* Lua 5.4 binding for nanovg API.
 * Function names match the nanovg C API one-to-one (no nvg_ prefix change),
 * mirroring the ../docs/nanovg-api.md surface.
 *
 * NVGcontext is exposed both as the global `vg` and as the implicit first
 * argument of every function (for compatibility with the doc snippets the
 * user copies in, which always pass the context explicitly).
 *
 * Colors are returned as 4-element float tables {r,g,b,a} in 0..1. Paints
 * are returned as opaque NVGpaint userdata. Image handles are integers.
 */

#include "lua_nvg.h"
#include <string.h>
#include <stdlib.h>
#include <math.h>

#define MT_PAINT "nvg.paint"
#define UPV_VG    lua_upvalueindex(1)

static NVGcontext *get_vg(lua_State *L) {
    /* Accept either explicit ctx as arg1 (lightuserdata) OR fall back to upvalue. */
    if (lua_islightuserdata(L, 1)) {
        NVGcontext *vg = (NVGcontext *)lua_touserdata(L, 1);
        lua_remove(L, 1);
        return vg;
    }
    return (NVGcontext *)lua_touserdata(L, UPV_VG);
}

/* ---------- color helpers ---------- */

static void push_color(lua_State *L, NVGcolor c) {
    lua_createtable(L, 0, 4);
    lua_pushnumber(L, c.r); lua_setfield(L, -2, "r");
    lua_pushnumber(L, c.g); lua_setfield(L, -2, "g");
    lua_pushnumber(L, c.b); lua_setfield(L, -2, "b");
    lua_pushnumber(L, c.a); lua_setfield(L, -2, "a");
}

static NVGcolor check_color(lua_State *L, int idx) {
    NVGcolor c = {{{0,0,0,1}}};
    luaL_checktype(L, idx, LUA_TTABLE);
    lua_getfield(L, idx, "r"); c.r = (float)luaL_optnumber(L, -1, 0); lua_pop(L,1);
    lua_getfield(L, idx, "g"); c.g = (float)luaL_optnumber(L, -1, 0); lua_pop(L,1);
    lua_getfield(L, idx, "b"); c.b = (float)luaL_optnumber(L, -1, 0); lua_pop(L,1);
    lua_getfield(L, idx, "a"); c.a = (float)luaL_optnumber(L, -1, 1); lua_pop(L,1);
    return c;
}

static void push_paint(lua_State *L, NVGpaint p) {
    NVGpaint *u = (NVGpaint *)lua_newuserdatauv(L, sizeof(NVGpaint), 0);
    *u = p;
    luaL_setmetatable(L, MT_PAINT);
}

static NVGpaint check_paint(lua_State *L, int idx) {
    NVGpaint *p = (NVGpaint *)luaL_checkudata(L, idx, MT_PAINT);
    return *p;
}

/* ---------- color constructors ---------- */

static int l_RGB(lua_State *L) {
    int r = (int)luaL_checkinteger(L, 1);
    int g = (int)luaL_checkinteger(L, 2);
    int b = (int)luaL_checkinteger(L, 3);
    push_color(L, nvgRGB((unsigned char)r, (unsigned char)g, (unsigned char)b));
    return 1;
}
static int l_RGBA(lua_State *L) {
    int r = (int)luaL_checkinteger(L, 1);
    int g = (int)luaL_checkinteger(L, 2);
    int b = (int)luaL_checkinteger(L, 3);
    int a = (int)luaL_checkinteger(L, 4);
    push_color(L, nvgRGBA((unsigned char)r,(unsigned char)g,(unsigned char)b,(unsigned char)a));
    return 1;
}
static int l_RGBf(lua_State *L) {
    push_color(L, nvgRGBf((float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3)));
    return 1;
}
static int l_RGBAf(lua_State *L) {
    push_color(L, nvgRGBAf((float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4)));
    return 1;
}
static int l_HSL(lua_State *L) {
    push_color(L, nvgHSL((float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3)));
    return 1;
}
static int l_HSLA(lua_State *L) {
    push_color(L, nvgHSLA((float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(unsigned char)luaL_checkinteger(L,4)));
    return 1;
}
static int l_LerpRGBA(lua_State *L) {
    NVGcolor a = check_color(L, 1);
    NVGcolor b = check_color(L, 2);
    push_color(L, nvgLerpRGBA(a, b, (float)luaL_checknumber(L, 3)));
    return 1;
}
static int l_TransRGBA(lua_State *L) {
    NVGcolor c = check_color(L, 1);
    push_color(L, nvgTransRGBA(c, (unsigned char)luaL_checkinteger(L, 2)));
    return 1;
}
static int l_TransRGBAf(lua_State *L) {
    NVGcolor c = check_color(L, 1);
    push_color(L, nvgTransRGBAf(c, (float)luaL_checknumber(L, 2)));
    return 1;
}

/* ---------- frame / state ---------- */
#define VG_VOID(name, body) static int l_##name(lua_State *L){ NVGcontext *vg = get_vg(L); body; return 0; }

static int l_BeginFrame(lua_State *L) {
    NVGcontext *vg = get_vg(L);
    float w = (float)luaL_checknumber(L,1);
    float h = (float)luaL_checknumber(L,2);
    float dpr = (float)luaL_optnumber(L,3,1.0);
    nvgBeginFrame(vg, w, h, dpr);
    return 0;
}
VG_VOID(EndFrame,    nvgEndFrame(vg))
VG_VOID(CancelFrame, nvgCancelFrame(vg))
VG_VOID(Save,        nvgSave(vg))
VG_VOID(Restore,     nvgRestore(vg))
VG_VOID(Reset,       nvgReset(vg))

static int l_ShapeAntiAlias(lua_State *L){ NVGcontext *vg=get_vg(L); nvgShapeAntiAlias(vg,(int)luaL_checkinteger(L,1)); return 0; }
static int l_GlobalAlpha (lua_State *L){ NVGcontext *vg=get_vg(L); nvgGlobalAlpha (vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_MiterLimit  (lua_State *L){ NVGcontext *vg=get_vg(L); nvgMiterLimit  (vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_StrokeWidth (lua_State *L){ NVGcontext *vg=get_vg(L); nvgStrokeWidth (vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_LineCap     (lua_State *L){ NVGcontext *vg=get_vg(L); nvgLineCap     (vg,(int)luaL_checkinteger(L,1)); return 0; }
static int l_LineJoin    (lua_State *L){ NVGcontext *vg=get_vg(L); nvgLineJoin    (vg,(int)luaL_checkinteger(L,1)); return 0; }

/* ---------- transforms ---------- */
static int l_Translate(lua_State *L){ NVGcontext *vg=get_vg(L); nvgTranslate(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2)); return 0; }
static int l_Scale    (lua_State *L){ NVGcontext *vg=get_vg(L); nvgScale    (vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2)); return 0; }
static int l_Rotate   (lua_State *L){ NVGcontext *vg=get_vg(L); nvgRotate   (vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_SkewX    (lua_State *L){ NVGcontext *vg=get_vg(L); nvgSkewX    (vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_SkewY    (lua_State *L){ NVGcontext *vg=get_vg(L); nvgSkewY    (vg,(float)luaL_checknumber(L,1)); return 0; }
VG_VOID(ResetTransform, nvgResetTransform(vg))
static int l_Transform(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgTransform(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),
                    (float)luaL_checknumber(L,4),(float)luaL_checknumber(L,5),(float)luaL_checknumber(L,6));
    return 0; }
static int l_DegToRad(lua_State *L){ lua_pushnumber(L, nvgDegToRad((float)luaL_checknumber(L,1))); return 1; }
static int l_RadToDeg(lua_State *L){ lua_pushnumber(L, nvgRadToDeg((float)luaL_checknumber(L,1))); return 1; }

/* ---------- path / shapes ---------- */
VG_VOID(BeginPath, nvgBeginPath(vg))
VG_VOID(ClosePath, nvgClosePath(vg))
static int l_MoveTo  (lua_State *L){ NVGcontext *vg=get_vg(L); nvgMoveTo  (vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2)); return 0; }
static int l_LineTo  (lua_State *L){ NVGcontext *vg=get_vg(L); nvgLineTo  (vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2)); return 0; }
static int l_BezierTo(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgBezierTo(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),
                   (float)luaL_checknumber(L,4),(float)luaL_checknumber(L,5),(float)luaL_checknumber(L,6));
    return 0; }
static int l_QuadTo(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgQuadTo(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4));
    return 0; }
static int l_ArcTo(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgArcTo(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),
                (float)luaL_checknumber(L,4),(float)luaL_checknumber(L,5));
    return 0; }
static int l_PathWinding(lua_State *L){ NVGcontext *vg=get_vg(L); nvgPathWinding(vg,(int)luaL_checkinteger(L,1)); return 0; }

static int l_Rect(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgRect(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4));
    return 0; }
static int l_RoundedRect(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgRoundedRect(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4),(float)luaL_checknumber(L,5));
    return 0; }
static int l_RoundedRectVarying(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgRoundedRectVarying(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4),
                             (float)luaL_checknumber(L,5),(float)luaL_checknumber(L,6),(float)luaL_checknumber(L,7),(float)luaL_checknumber(L,8));
    return 0; }
static int l_Circle(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgCircle(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3));
    return 0; }
static int l_Ellipse(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgEllipse(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4));
    return 0; }
static int l_Arc(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgArc(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),
              (float)luaL_checknumber(L,4),(float)luaL_checknumber(L,5),(int)luaL_checkinteger(L,6));
    return 0; }

/* ---------- fill/stroke ---------- */
static int l_FillColor  (lua_State *L){ NVGcontext *vg=get_vg(L); nvgFillColor  (vg, check_color(L,1)); return 0; }
static int l_StrokeColor(lua_State *L){ NVGcontext *vg=get_vg(L); nvgStrokeColor(vg, check_color(L,1)); return 0; }
static int l_FillPaint  (lua_State *L){ NVGcontext *vg=get_vg(L); nvgFillPaint  (vg, check_paint(L,1)); return 0; }
static int l_StrokePaint(lua_State *L){ NVGcontext *vg=get_vg(L); nvgStrokePaint(vg, check_paint(L,1)); return 0; }
VG_VOID(Fill,   nvgFill(vg))
VG_VOID(Stroke, nvgStroke(vg))

/* ---------- gradients ---------- */
static int l_LinearGradient(lua_State *L){ NVGcontext *vg=get_vg(L);
    NVGpaint p = nvgLinearGradient(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),
                                       (float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4),
                                       check_color(L,5), check_color(L,6));
    push_paint(L, p); return 1; }
static int l_RadialGradient(lua_State *L){ NVGcontext *vg=get_vg(L);
    NVGpaint p = nvgRadialGradient(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),
                                       (float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4),
                                       check_color(L,5), check_color(L,6));
    push_paint(L, p); return 1; }
static int l_BoxGradient(lua_State *L){ NVGcontext *vg=get_vg(L);
    NVGpaint p = nvgBoxGradient(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),
                                    (float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4),
                                    (float)luaL_checknumber(L,5),(float)luaL_checknumber(L,6),
                                    check_color(L,7), check_color(L,8));
    push_paint(L, p); return 1; }
static int l_ImagePattern(lua_State *L){ NVGcontext *vg=get_vg(L);
    NVGpaint p = nvgImagePattern(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),
                                     (float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4),
                                     (float)luaL_checknumber(L,5),(int)luaL_checkinteger(L,6),
                                     (float)luaL_checknumber(L,7));
    push_paint(L, p); return 1; }

/* ---------- scissor ---------- */
static int l_Scissor(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgScissor(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4));
    return 0; }
static int l_IntersectScissor(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgIntersectScissor(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),(float)luaL_checknumber(L,3),(float)luaL_checknumber(L,4));
    return 0; }
VG_VOID(ResetScissor, nvgResetScissor(vg))

/* ---------- images ---------- */
/* Image lookup happens relative to the assets dir set by host via a closure upvalue.
 * Path resolution is done in Lua using package.path-like semantics in main.c;
 * here we just call nanovg with the already-resolved path string. */
static int l_CreateImage(lua_State *L){ NVGcontext *vg=get_vg(L);
    const char *path = luaL_checkstring(L,1);
    int flags = (int)luaL_optinteger(L,2,0);
    lua_pushinteger(L, nvgCreateImage(vg, path, flags));
    return 1; }
static int l_DeleteImage(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgDeleteImage(vg,(int)luaL_checkinteger(L,1));
    return 0; }
static int l_ImageSize(lua_State *L){ NVGcontext *vg=get_vg(L);
    int w=0,h=0; nvgImageSize(vg,(int)luaL_checkinteger(L,1),&w,&h);
    lua_pushinteger(L,w); lua_pushinteger(L,h); return 2; }

/* ---------- fonts / text ---------- */
static int l_CreateFont(lua_State *L){ NVGcontext *vg=get_vg(L);
    const char *name = luaL_checkstring(L,1);
    const char *file = luaL_checkstring(L,2);
    lua_pushinteger(L, nvgCreateFont(vg, name, file));
    return 1; }
static int l_FindFont(lua_State *L){ NVGcontext *vg=get_vg(L);
    lua_pushinteger(L, nvgFindFont(vg, luaL_checkstring(L,1))); return 1; }
static int l_AddFallbackFontId(lua_State *L){ NVGcontext *vg=get_vg(L);
    lua_pushinteger(L, nvgAddFallbackFontId(vg,(int)luaL_checkinteger(L,1),(int)luaL_checkinteger(L,2))); return 1; }
static int l_AddFallbackFont(lua_State *L){ NVGcontext *vg=get_vg(L);
    lua_pushinteger(L, nvgAddFallbackFont(vg, luaL_checkstring(L,1), luaL_checkstring(L,2))); return 1; }
static int l_FontFace(lua_State *L){ NVGcontext *vg=get_vg(L); nvgFontFace(vg, luaL_checkstring(L,1)); return 0; }
static int l_FontFaceId(lua_State *L){ NVGcontext *vg=get_vg(L); nvgFontFaceId(vg,(int)luaL_checkinteger(L,1)); return 0; }
static int l_FontSize(lua_State *L){ NVGcontext *vg=get_vg(L); nvgFontSize(vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_FontBlur(lua_State *L){ NVGcontext *vg=get_vg(L); nvgFontBlur(vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_TextLetterSpacing(lua_State *L){ NVGcontext *vg=get_vg(L); nvgTextLetterSpacing(vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_TextLineHeight(lua_State *L){ NVGcontext *vg=get_vg(L); nvgTextLineHeight(vg,(float)luaL_checknumber(L,1)); return 0; }
static int l_TextAlign(lua_State *L){ NVGcontext *vg=get_vg(L); nvgTextAlign(vg,(int)luaL_checkinteger(L,1)); return 0; }

static int l_Text(lua_State *L){ NVGcontext *vg=get_vg(L);
    float x=(float)luaL_checknumber(L,1), y=(float)luaL_checknumber(L,2);
    const char *s = luaL_checkstring(L,3);
    float adv = nvgText(vg,x,y,s,NULL);
    lua_pushnumber(L,adv); return 1; }
static int l_TextBox(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgTextBox(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),
                  (float)luaL_checknumber(L,3), luaL_checkstring(L,4), NULL);
    return 0; }
static int l_TextBounds(lua_State *L){ NVGcontext *vg=get_vg(L);
    float bounds[4]={0};
    float adv = nvgTextBounds(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),
                                  luaL_checkstring(L,3), NULL, bounds);
    lua_pushnumber(L, adv);
    lua_createtable(L, 4, 0);
    for (int i=0;i<4;i++){ lua_pushnumber(L, bounds[i]); lua_rawseti(L,-2,i+1); }
    return 2; }
static int l_TextBoxBounds(lua_State *L){ NVGcontext *vg=get_vg(L);
    float bounds[4]={0};
    nvgTextBoxBounds(vg,(float)luaL_checknumber(L,1),(float)luaL_checknumber(L,2),
                        (float)luaL_checknumber(L,3), luaL_checkstring(L,4), NULL, bounds);
    lua_createtable(L, 4, 0);
    for (int i=0;i<4;i++){ lua_pushnumber(L, bounds[i]); lua_rawseti(L,-2,i+1); }
    return 1; }
static int l_TextMetrics(lua_State *L){ NVGcontext *vg=get_vg(L);
    float a=0,d=0,h=0; nvgTextMetrics(vg,&a,&d,&h);
    lua_pushnumber(L,a); lua_pushnumber(L,d); lua_pushnumber(L,h); return 3; }

/* ---------- composite ---------- */
static int l_GlobalCompositeOperation(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgGlobalCompositeOperation(vg,(int)luaL_checkinteger(L,1)); return 0; }
static int l_GlobalCompositeBlendFunc(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgGlobalCompositeBlendFunc(vg,(int)luaL_checkinteger(L,1),(int)luaL_checkinteger(L,2)); return 0; }
static int l_GlobalCompositeBlendFuncSeparate(lua_State *L){ NVGcontext *vg=get_vg(L);
    nvgGlobalCompositeBlendFuncSeparate(vg,(int)luaL_checkinteger(L,1),(int)luaL_checkinteger(L,2),
                                            (int)luaL_checkinteger(L,3),(int)luaL_checkinteger(L,4)); return 0; }

/* ---------- TapTap-only stubs (no-op so user scripts don't crash) ---------- */
static int l_NoOp(lua_State *L){ (void)L; return 0; }

/* ---------- registry ---------- */

#define R(name) { "nvg" #name, l_##name }
static const luaL_Reg fns[] = {
    /* color */
    R(RGB), R(RGBA), R(RGBf), R(RGBAf), R(HSL), R(HSLA), R(LerpRGBA), R(TransRGBA), R(TransRGBAf),
    /* frame/state */
    R(BeginFrame), R(EndFrame), R(CancelFrame),
    R(Save), R(Restore), R(Reset),
    R(ShapeAntiAlias), R(GlobalAlpha), R(MiterLimit),
    R(StrokeWidth), R(LineCap), R(LineJoin),
    /* transform */
    R(Translate), R(Scale), R(Rotate), R(SkewX), R(SkewY),
    R(ResetTransform), R(Transform), R(DegToRad), R(RadToDeg),
    /* path */
    R(BeginPath), R(ClosePath), R(MoveTo), R(LineTo), R(BezierTo), R(QuadTo), R(ArcTo), R(PathWinding),
    R(Rect), R(RoundedRect), R(RoundedRectVarying), R(Circle), R(Ellipse), R(Arc),
    /* fill/stroke */
    R(FillColor), R(StrokeColor), R(FillPaint), R(StrokePaint), R(Fill), R(Stroke),
    /* gradients */
    R(LinearGradient), R(RadialGradient), R(BoxGradient), R(ImagePattern),
    /* scissor */
    R(Scissor), R(IntersectScissor), R(ResetScissor),
    /* images */
    R(CreateImage), R(DeleteImage), R(ImageSize),
    /* fonts/text */
    R(CreateFont), R(FindFont), R(AddFallbackFontId), R(AddFallbackFont),
    R(FontFace), R(FontFaceId), R(FontSize), R(FontBlur),
    R(TextLetterSpacing), R(TextLineHeight), R(TextAlign),
    R(Text), R(TextBox), R(TextBounds), R(TextBoxBounds), R(TextMetrics),
    /* composite */
    R(GlobalCompositeOperation), R(GlobalCompositeBlendFunc), R(GlobalCompositeBlendFuncSeparate),
    { NULL, NULL }
};
#undef R

/* TapTap-private extensions present in BaiSiYeShou but not in upstream nanovg.
 * We expose them as no-ops so scripts copy-pasted from the game don't error. */
static const char *noop_names[] = {
    "nvgCreate", "nvgDelete",
    "nvgSetBloomEnabled", "nvgSetColorSpace", "nvgSetRenderTarget", "nvgSetRenderOrder",
    "nvgImagePatternTinted",
    "nvgCreateVideo", "nvgDeleteVideo",
    "nvgEllipseArc",
    "nvgForceAutoHint", "nvgGetForceAutoHint",
    "nvgFontSizeMethod", "nvgGetFontSizeMethod",
    "nvgCurrentTransform",
    "nvgTransformIdentity", "nvgTransformTranslate", "nvgTransformScale",
    "nvgTransformRotate", "nvgTransformSkewX", "nvgTransformSkewY",
    NULL
};

struct ConstDef { const char *name; lua_Integer value; };
static const struct ConstDef consts[] = {
    /* winding / solidity */
    {"NVG_CCW", NVG_CCW}, {"NVG_CW", NVG_CW},
    {"NVG_SOLID", NVG_SOLID}, {"NVG_HOLE", NVG_HOLE},
    /* line cap/join */
    {"NVG_BUTT", NVG_BUTT}, {"NVG_ROUND", NVG_ROUND}, {"NVG_SQUARE", NVG_SQUARE},
    {"NVG_BEVEL", NVG_BEVEL}, {"NVG_MITER", NVG_MITER},
    /* align */
    {"NVG_ALIGN_LEFT",   NVG_ALIGN_LEFT},
    {"NVG_ALIGN_CENTER", NVG_ALIGN_CENTER},
    {"NVG_ALIGN_RIGHT",  NVG_ALIGN_RIGHT},
    {"NVG_ALIGN_TOP",    NVG_ALIGN_TOP},
    {"NVG_ALIGN_MIDDLE", NVG_ALIGN_MIDDLE},
    {"NVG_ALIGN_BOTTOM", NVG_ALIGN_BOTTOM},
    {"NVG_ALIGN_BASELINE", NVG_ALIGN_BASELINE},
    {"NVG_ALIGN_CENTER_VISUAL", 1<<7},
    /* image flags */
    {"NVG_IMAGE_GENERATE_MIPMAPS", NVG_IMAGE_GENERATE_MIPMAPS},
    {"NVG_IMAGE_REPEATX", NVG_IMAGE_REPEATX},
    {"NVG_IMAGE_REPEATY", NVG_IMAGE_REPEATY},
    {"NVG_IMAGE_FLIPY",   NVG_IMAGE_FLIPY},
    {"NVG_IMAGE_PREMULTIPLIED", NVG_IMAGE_PREMULTIPLIED},
    {"NVG_IMAGE_NEAREST", NVG_IMAGE_NEAREST},
    /* composite operations */
    {"NVG_SOURCE_OVER", NVG_SOURCE_OVER},
    {"NVG_SOURCE_IN",   NVG_SOURCE_IN},
    {"NVG_SOURCE_OUT",  NVG_SOURCE_OUT},
    {"NVG_ATOP",        NVG_ATOP},
    {"NVG_DESTINATION_OVER", NVG_DESTINATION_OVER},
    {"NVG_DESTINATION_IN",   NVG_DESTINATION_IN},
    {"NVG_DESTINATION_OUT",  NVG_DESTINATION_OUT},
    {"NVG_DESTINATION_ATOP", NVG_DESTINATION_ATOP},
    {"NVG_LIGHTER",     NVG_LIGHTER},
    {"NVG_COPY",        NVG_COPY},
    {"NVG_XOR",         NVG_XOR},
    /* blend factors */
    {"NVG_ZERO", NVG_ZERO}, {"NVG_ONE", NVG_ONE},
    {"NVG_SRC_COLOR", NVG_SRC_COLOR}, {"NVG_ONE_MINUS_SRC_COLOR", NVG_ONE_MINUS_SRC_COLOR},
    {"NVG_DST_COLOR", NVG_DST_COLOR}, {"NVG_ONE_MINUS_DST_COLOR", NVG_ONE_MINUS_DST_COLOR},
    {"NVG_SRC_ALPHA", NVG_SRC_ALPHA}, {"NVG_ONE_MINUS_SRC_ALPHA", NVG_ONE_MINUS_SRC_ALPHA},
    {"NVG_DST_ALPHA", NVG_DST_ALPHA}, {"NVG_ONE_MINUS_DST_ALPHA", NVG_ONE_MINUS_DST_ALPHA},
    {"NVG_SRC_ALPHA_SATURATE", NVG_SRC_ALPHA_SATURATE},
    /* TapTap-only color space (no-op) */
    {"NVG_COLOR_GAMMA", 0}, {"NVG_COLOR_LINEAR", 1},
    {"NVG_SIZE_PIXEL",  0}, {"NVG_SIZE_CHAR",   1},
    { NULL, 0 }
};

void lua_nvg_open(lua_State *L, NVGcontext *vg) {
    /* paint metatable */
    if (luaL_newmetatable(L, MT_PAINT)) {
        /* no methods needed */
    }
    lua_pop(L, 1);

    /* register all functions as globals, with vg as upvalue */
    for (const luaL_Reg *r = fns; r->name; r++) {
        lua_pushlightuserdata(L, vg);
        lua_pushcclosure(L, r->func, 1);
        lua_setglobal(L, r->name);
    }

    /* register no-op stubs */
    for (const char **n = noop_names; *n; n++) {
        lua_pushcfunction(L, l_NoOp);
        lua_setglobal(L, *n);
    }

    /* constants */
    for (const struct ConstDef *c = consts; c->name; c++) {
        lua_pushinteger(L, c->value);
        lua_setglobal(L, c->name);
    }

    /* expose vg as global lightuserdata */
    lua_pushlightuserdata(L, vg);
    lua_setglobal(L, "vg");
}
