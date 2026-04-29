"""F1 调试叠层：FPS + 当前场景 id + 场景目录（按 phase 分组、可点击跳转）。

设计：
- 完全用 pygame 自己绘制（不进 Lua），叠在屏幕最上层
- 状态：visible（F1 切换）、hover_idx、collapsed phases
- on_click 通过回调回到 run.py 触发 _enter_scene
"""
from __future__ import annotations

import pygame
from typing import Callable, Dict, List


class Overlay:
    def __init__(
        self,
        scenes_grouped: Dict[str, List[Dict[str, str]]],
        font: pygame.font.Font,
        small_font: pygame.font.Font,
        on_pick: Callable[[str], None],
    ):
        self.groups = scenes_grouped
        self.font = font
        self.small = small_font
        self.on_pick = on_pick
        self.visible = False
        self.fps = 0.0
        self.current_scene = "?"
        self._rects: List[tuple] = []  # [(rect, scene_id), ...]
        self.mouse_pos = (0, 0)  # 设计画布坐标（外部每帧更新）

    def toggle(self):
        self.visible = not self.visible

    def set_fps(self, fps: float):
        self.fps = fps

    def set_current(self, sid: str):
        self.current_scene = sid or "?"

    def handle_event(self, ev: pygame.event.Event) -> bool:
        """返回 True 表示事件已被叠层吞掉。"""
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F1:
            self.toggle()
            return True
        if not self.visible:
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for rect, sid in self._rects:
                if rect.collidepoint(ev.pos):
                    self.on_pick(sid)
                    return True
        return False

    def draw(self, surf: pygame.Surface):
        # 角标始终显示一行小字（FPS + scene + F1 提示）
        line = f"FPS {self.fps:5.1f}  scene={self.current_scene}  [F1] menu"
        img = self.small.render(line, True, (220, 220, 220))
        bg = pygame.Surface((img.get_width() + 12, img.get_height() + 6), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 140))
        surf.blit(bg, (4, 4))
        surf.blit(img, (10, 7))

        if not self.visible:
            self._rects = []
            return

        # 半透明遮罩 + 面板
        W, H = surf.get_size()
        mask = pygame.Surface((W, H), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 120))
        surf.blit(mask, (0, 0))

        panel_w = 360
        panel_h = min(H - 80, 600)
        px, py = 20, 40
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((25, 28, 40, 230))
        pygame.draw.rect(panel, (90, 110, 160), panel.get_rect(), 1)
        surf.blit(panel, (px, py))

        # 标题
        title = self.font.render("Scenes", True, (240, 240, 240))
        surf.blit(title, (px + 12, py + 8))

        # 列出
        self._rects = []
        mx, my = self.mouse_pos
        y = py + 44
        for phase, items in self.groups.items():
            ph = self.small.render(f"[{phase}]", True, (140, 180, 255))
            surf.blit(ph, (px + 12, y))
            y += 22
            for it in items:
                sid = it["id"]
                rect = pygame.Rect(px + 24, y, panel_w - 36, 22)
                hovered = rect.collidepoint(mx, my)
                if hovered:
                    pygame.draw.rect(surf, (60, 90, 150, 200), rect)
                color = (255, 255, 180) if sid == self.current_scene else (220, 220, 220)
                lbl = self.small.render(sid, True, color)
                surf.blit(lbl, (rect.x + 6, rect.y + 4))
                self._rects.append((rect, sid))
                y += 22
                if y > py + panel_h - 24:
                    return
            y += 6
