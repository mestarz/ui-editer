"""run.py — Lua 预览器入口。

用法：
    python run.py [--game-root ../../BaiSiYeShou] [--scale 1.0]
"""
import argparse
import os
import sys
import time
import traceback

import pygame
import lupa

# 让 engine_shim 模块可被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine_shim import nvg, constants, stubs, asset, input as input_mod, events, loader, scenes_index  # noqa: E402
from engine_shim.overlay import Overlay  # noqa: E402
from engine_shim.hotreload import HotReloader  # noqa: E402


DESIGN_W = 1280
DESIGN_H = 720


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--game-root", default=os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "BaiSiYeShou")),
        help="BaiSiYeShou 根目录")
    p.add_argument("--scale", type=float, default=1.0, help="窗口缩放（设计 1280x720 × scale）")
    p.add_argument("--window-scale", type=float, default=1.5, help="窗口放大倍数（不影响游戏内坐标，仅 blit 时放大）")
    p.add_argument("--no-main", action="store_true", help="跳过 main.lua，仅渲染占位图（M1 自检）")
    p.add_argument("--snapshot", default=None, help="跑 N 帧后保存截图到该路径并退出（debug 用）")
    p.add_argument("--snapshot-frames", type=int, default=30)
    p.add_argument("--scene", default=None, help="启动后强制跳转到该场景 id（见 scenes/Registry.lua）")
    p.add_argument("--no-reload", action="store_true", help="禁用热重载（默认开启）")
    return p.parse_args()


def main():
    args = parse_args()
    win_w = int(DESIGN_W * args.scale)
    win_h = int(DESIGN_H * args.scale)

    pygame.init()
    pygame.display.set_caption("BaiSiYeShou — Lua Preview (P1)")
    # 物理窗口 = design × window_scale；游戏内绘制都画到 1280x720 的离屏画布，再 upscale-blit
    out_w = int(win_w * args.window_scale)
    out_h = int(win_h * args.window_scale)
    window = pygame.display.set_mode((out_w, out_h), pygame.RESIZABLE)
    screen = pygame.Surface((win_w, win_h)).convert_alpha()  # 设计画布
    clock = pygame.time.Clock()

    # ── Lua 运行时 ────────────────────────────────
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)

    scripts_root = os.path.join(args.game_root, "scripts")
    asset_root = os.path.join(args.game_root, "assets")
    if not os.path.isdir(scripts_root):
        print(f"ERROR: 未找到 scripts/: {scripts_root}")
        sys.exit(1)

    asset_loader = asset.AssetLoader(asset_root)
    font_loader  = asset.FontLoader(asset_root)
    # 预注册 "sans" → 触发 CJK 降级，让 overlay 也能显示中文
    font_loader.register("sans", "Fonts/MiSans-Regular.ttf")

    # NVG 上下文（绑定到 screen）
    vg_handle = nvg.nvg_create_context(screen, asset_loader, font_loader)

    # 把所有 shim 装进 Lua 全局
    constants.install(lua)
    nvg.install(lua)
    inp, gr = stubs.install(lua, win_w=win_w, win_h=win_h)
    bus = events.EventBus()
    lua.globals()["SubscribeToEvent"]   = bus.subscribe
    lua.globals()["UnsubscribeFromEvent"] = lambda *a, **kw: None
    lua.globals()["SendEvent"]          = lambda *a, **kw: None
    # 让 Lua 工作目录从 assets/ 出发（与引擎一致）
    os.chdir(asset_root) if os.path.isdir(asset_root) else None
    loader.install(lua, scripts_root)

    # ── 调试叠层（F1）────────────────────────────
    registry_path = os.path.join(scripts_root, "scenes", "Registry.lua")
    scenes_rows = scenes_index.parse(__import__("pathlib").Path(registry_path)) if os.path.isfile(registry_path) else []
    scenes_grouped = scenes_index.grouped(scenes_rows)
    ov_font = font_loader.get("sans", 18) or pygame.font.Font(None, 18)
    ov_small = font_loader.get("sans", 14) or pygame.font.Font(None, 14)
    overlay = Overlay(scenes_grouped, ov_font, ov_small, on_pick=lambda sid: _enter_scene(lua, sid))

    # ── 热重载（轮询 scripts/**/*.lua）────────────
    reloader = HotReloader(scripts_root) if not args.no_reload else None

    # ── 加载 main.lua ─────────────────────────────
    if not args.no_main:
        main_path = os.path.join(scripts_root, "main.lua")
        try:
            with open(main_path, "r", encoding="utf-8") as f:
                src = f.read()
            lua.execute(src)
            lua.globals()["Start"]()
            print("[run] main.lua Start() 调用完成")
            if args.scene:
                # 场景映射 → GameFlow.Enter*。home 等场景需要先 StartNewGame 才有合法状态。
                _enter_scene(lua, args.scene)
        except Exception as e:
            print("[run] 加载/启动 main.lua 失败：", e)
            traceback.print_exc()
            args.no_main = True  # 降级：进占位渲染循环

    # ── 主循环 ────────────────────────────────────
    last_t = time.time()
    running = True
    frame_idx = 0
    while running:
        now = time.time()
        dt = now - last_t
        last_t = now
        # 清掉上一帧的单帧 press 状态；本帧事件再补进去
        input_mod.begin_frame(inp)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                continue
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                running = False
                continue
            # 鼠标事件：从物理窗口坐标反算回设计坐标
            ww, wh = window.get_size()
            sx = win_w / ww if ww > 0 else 1.0
            sy = win_h / wh if wh > 0 else 1.0
            if ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                ev.pos = (int(ev.pos[0] * sx), int(ev.pos[1] * sy))
            # 叠层优先吃事件（F1 切换 / 菜单点击）
            if overlay.handle_event(ev):
                continue
            if ev.type == pygame.MOUSEMOTION:
                overlay.mouse_pos = ev.pos
                input_mod.update_mouse_pos(inp, ev.pos[0], ev.pos[1])
                bus.fire(lua, "MouseMove", {"X": _IntVar(ev.pos[0]), "Y": _IntVar(ev.pos[1])})
            input_mod.feed_pygame_event(inp, ev)

        # 帧首：清屏 + 帧状态
        screen.fill((0, 0, 0))

        if not args.no_main:
            try:
                bus.fire(lua, "Update", {"TimeStep": _FloatVar(dt)})
                bus.fire(lua, "NanoVGRender", {})
            except Exception as e:
                print("[run] 帧异常：", e)
                traceback.print_exc()
        else:
            # M1 自检：直接画一段文字证明窗口活着
            f = font_loader.get("sans", 32)
            if f is None:
                # 系统字体退路
                f = pygame.font.Font(None, 32)
            img = f.render("Lua Preview ready (--no-main)", True, (200, 220, 255))
            screen.blit(img, (40, 40))

        # 叠层（绘制在 Lua 帧之上）
        try:
            cur_id = lua.eval('require("SceneManager").Current()')
            if cur_id is not None:
                overlay.set_current(str(cur_id))
        except Exception:
            pass
        overlay.set_fps(clock.get_fps())
        overlay.draw(screen)

        # 热重载
        if reloader is not None:
            changed = reloader.poll()
            if changed:
                print(f"[hotreload] 检测到 {len(changed)} 个 .lua 变更，重载中…")
                reloader.reload(lua, overlay.current_scene if overlay.current_scene != "?" else None, _enter_scene)

        # 把设计画布按窗口大小 upscale 到物理窗口
        cur_size = window.get_size()
        if cur_size == (win_w, win_h):
            window.blit(screen, (0, 0))
        else:
            scaled = pygame.transform.smoothscale(screen, cur_size)
            window.blit(scaled, (0, 0))
        pygame.display.flip()
        frame_idx += 1
        if args.snapshot and frame_idx >= args.snapshot_frames:
            pygame.image.save(screen, args.snapshot)
            print(f"[run] 截图已保存到 {args.snapshot}")
            running = False
        clock.tick(60)

    # ── 退出 ──────────────────────────────────────
    try:
        if not args.no_main:
            stop = lua.globals()["Stop"]
            if stop: stop()
    except Exception:
        pass
    pygame.quit()


def _enter_scene(lua, scene_id: str):
    """跳到 scene_id 之前确保游戏状态已初始化。"""
    # 需要 NewGame 状态的场景白名单（区别于 title/gallery）
    needs_new_game = scene_id not in ("title", "gallery")
    snippet_lines = ['local GF = require("GameFlow")', 'local SM = require("SceneManager")']
    if needs_new_game:
        snippet_lines.append('GF.StartNewGame("civilian_f_1")')
    enter_map = {
        "home":         'GF.EnterHome()',
        "area_select":  'GF.EnterAreaSelect()',
        "party_select": 'GF.EnterPartySelect()',
        "explore":      'GF.EnterExplore()',
        "battle":       'GF.EnterBattle({})',
        "base":         'GF.EnterBase()',
        "placement":    'GF.EnterPlacement()',
        "defense":      'GF.EnterDefense()',
        "title":        'GF.EnterTitle()',
        "gallery":      'GF.EnterGallery()',
    }
    snippet_lines.append(enter_map.get(scene_id, f'SM.GoTo("{scene_id}")'))
    code = "\n".join(snippet_lines)
    try:
        lua.execute(code)
        print(f"[run] 跳转到场景: {scene_id}")
    except Exception as e:
        print(f"[run] 场景跳转失败 ({scene_id}): {e}")


# ─── EventData 仿真 ────────────────────────────────
# 引擎在事件中用 eventData["X"]:GetInt()；这里造一个简易包装。
class _IntVar:
    def __init__(self, v): self._v = int(v)
    def GetInt(self): return self._v
    def GetFloat(self): return float(self._v)


class _FloatVar:
    def __init__(self, v): self._v = float(v)
    def GetFloat(self): return self._v
    def GetInt(self): return int(self._v)


if __name__ == "__main__":
    main()
