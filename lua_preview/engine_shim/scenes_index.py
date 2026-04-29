"""解析 scripts/scenes/Registry.lua → 场景列表（按 phase 分组）。

正则解析即可，避免再启 lua 实例。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List


_ROW_RE = re.compile(
    r'\{\s*id\s*=\s*"(?P<id>[^"]+)"\s*,'
    r'\s*module\s*=\s*"(?P<mod>[^"]+)"'
    r'(?:\s*,\s*phase\s*=\s*GS\.PHASE_(?P<phase>\w+))?'
)


def parse(registry_path: Path) -> List[Dict[str, str]]:
    text = registry_path.read_text(encoding="utf-8")
    rows = []
    for m in _ROW_RE.finditer(text):
        rows.append({
            "id": m.group("id"),
            "module": m.group("mod"),
            "phase": (m.group("phase") or "MISC").lower(),
        })
    return rows


def grouped(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        out.setdefault(r["phase"], []).append(r)
    return out
