"""引擎不可或缺、但与 UI 预览无关的功能 stub。

包含：Scene / Octree / SoundSource / File / fileSystem / cjson / cache / SFX 节点。
全部不抛错、返回合理空值即可。
"""
import json
import os
from typing import Any


class _LuaCallableTable:
    """允许 Lua 用冒号语法调用：obj:Method() —— Python 侧用普通方法即可。"""

    def __getattr__(self, name):  # 默认所有未实现方法 → no-op
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **kw: None


class Node(_LuaCallableTable):
    def CreateChild(self, _name=None): return Node()
    def CreateComponent(self, _kind=None): return Component()


class Component(_LuaCallableTable):
    soundType = ""
    gain = 1.0
    autoRemoveMode = 0
    def Play(self, *_a, **_kw): pass


class _SceneClass(Node):
    pass


def Scene_ctor():  # 给 Lua 调用 Scene() 用
    return _SceneClass()


# ─── File API ─────────────────────────────────────
class File:
    def __init__(self, path, mode):
        self._path = path
        self._mode = mode
        self._buf = ""
        self._open = False
        if mode == 0 and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self._buf = f.read()
            self._open = True
        elif mode == 1:
            self._open = True
    def IsOpen(self): return self._open
    def ReadString(self): return self._buf
    def WriteString(self, s):
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(s)
    def Close(self): self._open = False


class FileSystem:
    def FileExists(self, path):
        return os.path.exists(path)


class _CJson:
    def encode(self, t):
        return json.dumps(_lua_to_py(t))
    def decode(self, s):
        return _py_to_lua(json.loads(s))


_lua_runtime = None  # set by install()


def _lua_to_py(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if hasattr(v, "items"):
        # Lua 表 → 试探数组/字典
        try:
            keys = list(v)
            is_arr = all(isinstance(k, int) and k >= 1 for k in keys) and keys == list(range(1, len(keys) + 1))
            if is_arr:
                return [_lua_to_py(v[k]) for k in keys]
            return {str(k): _lua_to_py(v[k]) for k in keys}
        except Exception:
            return None
    return v


def _py_to_lua(v):
    if isinstance(v, list):
        return _lua_runtime.table_from({i + 1: _py_to_lua(x) for i, x in enumerate(v)})
    if isinstance(v, dict):
        return _lua_runtime.table_from({k: _py_to_lua(x) for k, x in v.items()})
    return v


class _AttrMixin:
    """让 Python 对象在 Lua 里既能 obj:method() 也能 obj.field 访问。
    lupa 默认用 __getitem__ 处理 Lua 的 [] 索引；我们回退到 getattr，找不到返回 nil。

    注意：只在确实需要 [] 索引语义的对象上加（如 _Input 提供方法供 Lua : 调用）。
    单纯字段对象（如 _MousePos）不需要 mixin —— lupa 对纯 Python 对象的 obj.x 直接走属性访问，
    且 mixin 会让 lupa 把对象当 list-like 包装，长跑后会出现状态错乱。"""
    def __getitem__(self, key):
        if isinstance(key, str):
            v = getattr(self, key, None)
            return v
        raise KeyError(key)


# ─── ResourceCache stub ─────────────────────────────
class _Cache:
    def GetResource(self, kind, path):
        # 我们不实际加载 Sound（SFX 已 stub Play），返回非 None 让 SFX.Init 走完。
        return _LuaCallableTable()


# ─── input 全局对象（给 Input.lua 用）────────────────
class _MousePos:
    def __init__(self): self.x = 0; self.y = 0


class _Input(_AttrMixin):
    def __init__(self):
        self.mousePosition = _MousePos()
        self._keys_down = set()
        self._keys_press = set()
        self._mouse_down = set()
        self._mouse_press = set()
    def GetKeyDown(self, k): return k in self._keys_down
    def GetKeyPress(self, k): return k in self._keys_press
    def GetMouseButtonDown(self, b): return b in self._mouse_down
    def GetMouseButtonPress(self, b): return b in self._mouse_press


# ─── graphics 全局 ──────────────────────────────────
class _Graphics(_AttrMixin):
    def __init__(self, w, h, dpr=1.0):
        self._w, self._h, self._dpr = w, h, dpr
    def GetWidth(self): return self._w
    def GetHeight(self): return self._h
    def GetDPR(self): return self._dpr
    def resize(self, w, h):
        self._w, self._h = w, h


def install(lua, *, win_w, win_h):
    """把 stub 装进 Lua 全局。返回 (input, graphics) 句柄供主循环刷新。"""
    global _lua_runtime
    _lua_runtime = lua
    g = lua.globals()

    inp = _Input()
    gr = _Graphics(win_w, win_h)
    # mousePosition 用真正的 Lua table，避免 lupa 对自定义 __getitem__ 对象的长跑包装失稳
    inp.mousePosition = lua.table_from({"x": 0, "y": 0})

    g["graphics"] = gr
    g["input"]    = inp
    g["cache"]    = _Cache()
    g["fileSystem"] = FileSystem()
    g["cjson"]    = _CJson()
    g["File"]     = File
    g["Scene"]    = Scene_ctor
    # Octree / SoundSource 仅出现在 CreateComponent 的字符串参数里，无需符号
    return inp, gr
