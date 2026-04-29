"""引擎数值常量：键码、鼠标键、对齐位、混合模式等。

值都对齐 NanoVG / Urho3D 里的常量，但游戏代码只比较相等性，
所以只要保证唯一即可，无需复刻引擎数字。
"""
import pygame

# ─── NanoVG 文字对齐位（要可按位 OR）──────────────
NVG_ALIGN_LEFT     = 1 << 0
NVG_ALIGN_CENTER   = 1 << 1
NVG_ALIGN_RIGHT    = 1 << 2
NVG_ALIGN_TOP      = 1 << 3
NVG_ALIGN_MIDDLE   = 1 << 4
NVG_ALIGN_BOTTOM   = 1 << 5
NVG_ALIGN_BASELINE = 1 << 6

# ─── 复合混合模式 ─────────────────────────────────
NVG_SOURCE_OVER = 0
NVG_ATOP        = 1
NVG_SOURCE_ATOP = NVG_ATOP

# ─── 引擎杂项 ─────────────────────────────────────
REMOVE_COMPONENT = 1
FILE_READ  = 0
FILE_WRITE = 1

# ─── 鼠标键 ──────────────────────────────────────
MOUSEB_LEFT   = 1
MOUSEB_RIGHT  = 2
MOUSEB_MIDDLE = 4

# ─── 键盘：游戏代码引用了 KEY_A/D/E/F/J/R/S/W/UP/DOWN/LEFT/RIGHT/SPACE/LSHIFT/ESCAPE
#         直接映射到 pygame.K_*。
KEY_MAP = {
    "KEY_A":      pygame.K_a,
    "KEY_D":      pygame.K_d,
    "KEY_E":      pygame.K_e,
    "KEY_F":      pygame.K_f,
    "KEY_J":      pygame.K_j,
    "KEY_R":      pygame.K_r,
    "KEY_S":      pygame.K_s,
    "KEY_W":      pygame.K_w,
    "KEY_UP":     pygame.K_UP,
    "KEY_DOWN":   pygame.K_DOWN,
    "KEY_LEFT":   pygame.K_LEFT,
    "KEY_RIGHT":  pygame.K_RIGHT,
    "KEY_SPACE":  pygame.K_SPACE,
    "KEY_LSHIFT": pygame.K_LSHIFT,
    "KEY_ESCAPE": pygame.K_ESCAPE,
}


def install(lua):
    """把所有常量塞进 Lua 全局。"""
    g = lua.globals()
    for name, val in globals().items():
        if name.startswith(("NVG_", "KEY_", "MOUSEB_", "FILE_")) or name == "REMOVE_COMPONENT":
            g[name] = val
    for k, v in KEY_MAP.items():
        g[k] = v
