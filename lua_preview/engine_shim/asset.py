"""资产 / 字体加载器。

· AssetLoader：管理 nvgCreateImage 返回的 handle ↔ pygame.Surface。
  路径解析根目录由 run.py 设置（默认 BaiSiYeShou/assets，对齐引擎工作目录）。
· FontLoader：管理 nvgCreateFont 注册的 (name, ttf 路径)，按需 + 按字号缓存。
"""
import glob as _glob
import os
import subprocess
from typing import Dict, Optional, Tuple
import pygame


def _find_cjk_font() -> str:
    """在系统中查找一个支持 CJK 的字体文件路径，找不到返回空字符串。"""
    candidates = [
        # Arch Linux
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Light.ttc",
        "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
        # Ubuntu / Debian
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        # WSL — Windows 字体目录
        "/mnt/c/Windows/Fonts/msyh.ttc",          # 微软雅黑
        "/mnt/c/Windows/Fonts/NotoSansSC-VF.ttf", # Noto Sans SC（若安装）
        "/mnt/c/Windows/Fonts/simsun.ttc",         # 宋体
        "/mnt/c/Windows/Fonts/simhei.ttf",         # 黑体
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # 通配查找 Noto CJK 变体
    for pattern in (
        "/usr/share/fonts/**/NotoSansCJK*.ttc",
        "/usr/share/fonts/**/NotoSansSC*.otf",
        "/mnt/c/Windows/Fonts/Noto*CJK*.ttc",
    ):
        found = sorted(_glob.glob(pattern, recursive=True))
        if found:
            return found[0]
    # 最后用 fc-match 动态查找（排除不含 CJK 的 DejaVu 等回退字体）
    try:
        result = subprocess.run(
            ["fc-match", "--format=%{file}", ":lang=zh:spacing=proportional"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            p = result.stdout.strip()
            _non_cjk = ("DejaVu", "FreeSans", "Liberation", "Nimbus")
            if p and os.path.exists(p) and not any(x in p for x in _non_cjk):
                return p
    except Exception:
        pass
    return ""


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
        # 找不到游戏内字体时，降级查找系统 CJK 字体（保证中文不变方框）
        sys_cand = _find_cjk_font()
        if sys_cand:
            self._registered[name] = sys_cand
            print(f"[FontLoader] {rel_path} 不存在，降级使用 {sys_cand}")
            return 1
        print(f"[FontLoader] 未找到字体 {rel_path}，将使用 pygame 内置默认字体（CJK 可能无法显示）")
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
