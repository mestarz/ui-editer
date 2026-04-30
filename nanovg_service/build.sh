#!/usr/bin/env bash
# build.sh — 构建 C 渲染器
set -euo pipefail
cd "$(dirname "$0")/renderer"
mkdir -p build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc 2>/dev/null || echo 4)"
echo "[build] OK -> renderer/build/nvg_renderer"
