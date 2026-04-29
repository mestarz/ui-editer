"""资产 / 字体加载器。

· AssetLoader：管理 nvgCreateImage 返回的 handle ↔ pygame.Surface。
  路径解析根目录由 run.py 设置（默认 BaiSiYeShou/assets，对齐引擎工作目录）。
· FontLoader：管理 nvgCreateFont 注册的 (name, ttf 路径)，按需 + 按字号缓存。
"""
import os
from typing import Dict, Optional, Tuple
import pygame


class AssetLoader:
    def __init__(self, asset_root: str):
        self.asset_root = asset_root
        self._handle_to_surface: Dict[int, pygame.Surface] = {}
        self._path_to_handle: Dict[str, int] = {}
        self._next = 1

    def _resolve(self, rel: str) -> Optional[str]:
        candidates = [
            os.path.join(self.asset_root, rel),
            rel,  # 已是绝对路径或相对当前目录
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def create_image(self, path: str) -> int:
        if path in self._path_to_handle:
            return self._path_to_handle[path]
        full = self._resolve(path)
        if not full:
            print(f"[AssetLoader] 未找到资产: {path}")
            return -1
        try:
            surf = pygame.image.load(full).convert_alpha()
        except Exception as e:
            print(f"[AssetLoader] 加载失败 {full}: {e}")
            return -1
        h = self._next; self._next += 1
        self._handle_to_surface[h] = surf
        self._path_to_handle[path] = h
        return h

    def image_size(self, handle: int) -> Tuple[int, int]:
        surf = self._handle_to_surface.get(handle)
        if not surf:
            return (0, 0)
        return surf.get_width(), surf.get_height()

    def get_surface(self, handle: int) -> Optional[pygame.Surface]:
        return self._handle_to_surface.get(handle)

    def delete_image(self, handle: int):
        self._handle_to_surface.pop(handle, None)
        for p, h in list(self._path_to_handle.items()):
            if h == handle:
                self._path_to_handle.pop(p, None)


class FontLoader:
    def __init__(self, asset_root: str):
        self.asset_root = asset_root
        self._registered: Dict[str, str] = {}   # name -> ttf 绝对路径
        self._cache: Dict[Tuple[str, int], pygame.font.Font] = {}

    def register(self, name: str, rel_path: str) -> int:
        for cand in (os.path.join(self.asset_root, rel_path), rel_path):
            if os.path.exists(cand):
                self._registered[name] = cand
                return 1
        # 找不到 ttf 时降级查找系统 CJK 字体（保证中文不变方框）
        for sys_cand in (
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Light.ttc",
            "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
        ):
            if os.path.exists(sys_cand):
                self._registered[name] = sys_cand
                print(f"[FontLoader] {rel_path} 不存在，降级使用 {sys_cand}")
                return 1
        print(f"[FontLoader] 未找到字体 {rel_path}，将使用系统默认")
        self._registered[name] = ""
        return 1

    def get(self, name: str, size: int) -> Optional[pygame.font.Font]:
        path = self._registered.get(name, "")
        key = (name, size)
        f = self._cache.get(key)
        if f:
            return f
        try:
            f = pygame.font.Font(path or None, size)
        except Exception as e:
            print(f"[FontLoader] Font 创建失败 name={name} size={size}: {e}")
            f = pygame.font.Font(None, size)
        self._cache[key] = f
        return f
