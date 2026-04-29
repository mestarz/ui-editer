"""Lua 引擎事件系统 stub。

TapTap 引擎用 SubscribeToEvent("Update", "HandleUpdate") 这种字符串绑定回调。
本 shim 只追踪 main.lua 真正需要的两个事件：
    - "Update"        每帧前
    - "NanoVGRender"  每帧绘制
其它（"MouseMove" 等）也接住，但仅保存 handler，由 input shim 按需触发。
"""
from typing import Callable, Dict, List


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[str]] = {}

    def subscribe(self, *args):
        # 兼容两种签名：
        #   SubscribeToEvent(eventName, handlerName)
        #   SubscribeToEvent(sender, eventName, handlerName) —— 如 NanoVGRender 带 vg
        if len(args) == 2:
            event_name, handler_name = args
        elif len(args) == 3:
            _sender, event_name, handler_name = args
        else:
            raise TypeError(f"SubscribeToEvent: unexpected arity {len(args)}")
        self._handlers.setdefault(str(event_name), []).append(str(handler_name))

    def fire(self, lua, event_name: str, event_data: dict | None = None):
        handlers = self._handlers.get(event_name, [])
        if not handlers:
            return
        ed = lua.table_from(event_data or {})
        for h in handlers:
            fn = lua.globals()[h]
            if fn is None:
                continue
            try:
                # 用 xpcall 包裹拿到完整 Lua 栈
                runner = lua.eval(
                    'function(fn, ev, ed) '
                    '  local ok, err = xpcall(function() fn(ev, ed) end, '
                    '     function(e) return debug.traceback(tostring(e), 2) end) '
                    '  if not ok then return err else return nil end '
                    'end'
                )
                err = runner(fn, event_name, ed)
                if err is not None:
                    print(f"[event {event_name} → {h}]\n{err}")
            except Exception as e:
                print(f"[event {event_name} → {h}] outer Python: {type(e).__name__}: {e}")
