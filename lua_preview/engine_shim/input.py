"""把 pygame 事件投喂到 stubs._Input 实例（供 Lua Input 模块查询）。"""
from typing import Set
import pygame


def begin_frame(inp):
    inp._keys_press.clear()
    inp._mouse_press.clear()


def update_mouse_pos(inp, x, y):
    inp.mousePosition["x"] = x
    inp.mousePosition["y"] = y


def feed_pygame_event(inp, ev):
    if ev.type == pygame.KEYDOWN:
        inp._keys_down.add(ev.key)
        inp._keys_press.add(ev.key)
    elif ev.type == pygame.KEYUP:
        inp._keys_down.discard(ev.key)
    elif ev.type == pygame.MOUSEBUTTONDOWN:
        inp._mouse_down.add(ev.button)
        inp._mouse_press.add(ev.button)
    elif ev.type == pygame.MOUSEBUTTONUP:
        inp._mouse_down.discard(ev.button)
