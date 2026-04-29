"""Lua 脚本热重载：轮询 scripts/**/*.lua mtime，变更时清 package.loaded 并重跳当前场景。

用轮询而非 inotify/watchdog 是为了零依赖、跨平台一致。每秒扫一次（120 帧约扫 2 次）。
"""
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional


class HotReloader:
    def __init__(self, scripts_root: str, poll_interval: float = 1.0):
        self.root = scripts_root
        self.interval = poll_interval
        self._last_check = 0.0
        self._mtimes: Dict[str, float] = {}
        self._scan(initial=True)

    def _scan(self, initial: bool = False) -> List[str]:
        changed: List[str] = []
        for dirpath, _, files in os.walk(self.root):
            for fn in files:
                if not fn.endswith(".lua"):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                old = self._mtimes.get(p)
                self._mtimes[p] = mt
                if not initial and (old is None or mt > old):
                    changed.append(p)
        return changed

    def poll(self) -> List[str]:
        now = time.time()
        if now - self._last_check < self.interval:
            return []
        self._last_check = now
        return self._scan(initial=False)

    def reload(self, lua, current_scene: Optional[str], enter_scene_fn) -> bool:
        """清空 package.loaded 中所有 scripts/ 模块，重跑 main.lua，再回到 current_scene。"""
        try:
            # 清掉所有 scripts/ 下加载过的模块；保留标准库
            lua.execute('''
                for k,_ in pairs(package.loaded) do
                    if not (k == "string" or k == "table" or k == "math" or k == "io"
                         or k == "os" or k == "debug" or k == "coroutine" or k == "package") then
                        package.loaded[k] = nil
                    end
                end
            ''')
            # 重跑 main.lua（重新装 globals + Start）
            main_path = os.path.join(self.root, "main.lua")
            with open(main_path, "r", encoding="utf-8") as f:
                lua.execute(f.read())
            lua.globals()["Start"]()
            if current_scene:
                enter_scene_fn(lua, current_scene)
            return True
        except Exception as e:
            print(f"[hotreload] 重载失败：{e}")
            return False
